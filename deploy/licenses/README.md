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
| `CORRESPONDING-SOURCE.md`   | the LGPL-2.1 §6(d)/(c) obligation   | written here                                                                                    |

All retrieved 2026-07-31.

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
