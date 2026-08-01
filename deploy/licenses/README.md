# Licence texts shipped inside every Loft image

Everything in this directory is copied to `/app/licenses/` in the built images,
alongside the repo's `LICENSE` and `NOTICE`. It exists because publishing a
container image makes us a **distributor** of every byte inside it —
`uv sync` on a laptop does not (docs/LICENSING.md §1).

These are the texts that **no wheel ships**. Licence files that upstream wheels
_do_ carry are copied straight out of the installed environment at build time
by `scripts/check-licences.py --emit-inventory`, into
`/app/licenses/third-party/<distribution>/`, together with a generated
`THIRD-PARTY.md`. Nothing here is hand-maintained duplication of something a
wheel already provides.

| file                        | covers                              | retrieved from                                                                                |
| --------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------- |
| `LGPL-2.1.txt`              | OCCT, planegcs, LibRaw              | `Open-Cascade-SAS/OCCT` `LICENSE_LGPL_21.txt` — OCCT's own copy, so the provenance matches      |
| `OCCT_LGPL_EXCEPTION.txt`   | OCCT                                | `Open-Cascade-SAS/OCCT` `OCCT_LGPL_EXCEPTION.txt`                                               |
| `FTL.txt`                   | FreeType (our elected arm)          | `freetype/freetype` `docs/FTL.TXT`                                                              |
| `FreeImage-FIPL-1.0.txt`    | FreeImage (our elected arm)         | FreeImage `license-fi.txt`                                                                      |
| `MPL-2.0.txt`               | certifi                             | SPDX `license-list-data`                                                                        |
| `GPL-3.0.txt`               | libgomp, libgfortran, libquadmath   | `gcc-mirror/gcc` `COPYING3` @ `releases/gcc-8.5.0` (commit `eafe83f`) — GCC's own copy           |
| `GCC-RUNTIME-LIBRARY-EXCEPTION-3.1.txt` | the same three, and the reason they are here | `gcc-mirror/gcc` `COPYING.RUNTIME`, same commit                       |
| `CORRESPONDING-SOURCE.md`   | the LGPL-2.1 §6(d)/(c) obligation   | written here                                                                                    |
| `corresponding-source.json` | the machine-readable pin behind it  | written here; digests computed from real downloads (LIC-2, docs/LICENSING.md §10)              |

All retrieved 2026-07-31 (`corresponding-source.json` and the two GCC texts:
2026-08-01). Both GCC texts are byte-identical at the `releases/gcc-4.8.5`,
`releases/gcc-8.5.0` and `releases/gcc-15.2.0` tags — checked, because those are
the three GCC vintages whose runtime libraries this image actually carries, and
one text covering all three is a fact rather than an assumption.

**The GCC texts are here for a decision, not for a source offer.** `libgomp`,
`libgfortran` and `libquadmath` ship under GPL-3.0 **with** the Runtime Library
Exception, and Loft's position (`CORRESPONDING-SOURCE.md`, LIC-4) is that the
exception discharges the source duty for the only way we convey them: combined
with the Target Code that links them. Shipping the texts costs nothing and is
what tells a recipient which permission they hold; it is not an admission that
we owe GCC source, and it is not an invitation to delete the per-file records
in `corresponding-source.json` that make the position checkable.

`corresponding-source.json` is not documentation — `scripts/check-licences.py`
reads it on every `just lint`, in CI, and inside the image build, and fails when
the versions it pins stop matching the binaries in the tree. Editing a version
in it to make a build pass would be exactly backwards: the pin is the claim, the
binaries are the fact. Re-pin with `just corresponding-source-record <tag>` and
read the diff. Procedure: docs/LICENSING.md §7.

**The OCCT exception carries a duty, not just a permission.** It lets us
distribute object code incorporating OCCT header material under terms of our
choice *"provided that you give prominent notice in supporting documentation to
this code that it makes use of or is based on facilities provided by the Open
CASCADE Technology software."* That notice lives in the repo's `NOTICE`, which
is copied into the same directory in the image. Do not remove it.

**Dual-licensed components require an election, and silence is not one.**
FreeImage (FIPL-1.0 or GPL), FreeType (FTL or GPL-2.0), LibRaw (LGPL-2.1 or
CDDL-1.0) and zstd (BSD-3-Clause or GPL-2.0) are each offered under a choice;
`NOTICE` and `scripts/check-licences.py` record which arm Loft takes, and the
texts above are the ones for the arms we took.
