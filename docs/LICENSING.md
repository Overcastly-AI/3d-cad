# Licensing — can we publish container images?

> **This is an engineering analysis, not legal advice.** It is written by the
> project's maintainers to be acted on by the project's maintainers. Every
> claim below is checked against licence text or a command you can re-run in
> this repo; nothing here is recalled from folklore. If you are making a
> commercial redistribution decision, have a lawyer read it.

**Owner: `oss-curator`. Written 2026-07-31 against commit `04c74f0`.**

Publishing container images has been gated on this question for weeks. The
answer is below, up front.

---

## Recommendation

**Yes — but not all three images, and not today for one of them.**

| image        | verdict                                                          |
| ------------ | ---------------------------------------------------------------- |
| `gateway`    | **Publishable now.** Permissive-only closure. No copyleft at all. |
| `documents`  | **Publishable now.** Same.                                        |
| `geometry`   | **BLOCKED** until the five conditions below are done.             |

The geometry image is the only one that contains the kernel, and it is the
only one with a copyleft story. Its blocker is **not** OCCT — OCCT is fine and
our standing "LGPL-dynamic ok" position survives, with one correction about
_which_ LGPL clause we satisfy. Its blocker is a **GPL-2.0 library
(`libjbig`/jbigkit) vendored inside the OCP wheel**, which we would be
redistributing, and which our own policy forbids outright.

### The five conditions

1. **Remove jbigkit (GPL-2.0) from the geometry image.** See
   [P0 — jbigkit](#p0--jbigkit-gpl-20-is-vendored-inside-the-ocp-wheel). A
   verified, ~20-line fix exists and is described there.
2. **Ship the licence texts we are obliged to convey** into every image at
   `/app/licenses/` — LGPL-2.1 + the Open CASCADE exception (OCCT), LGPL-2.1
   (planegcs), MPL-2.0 (certifi), FIPL-1.0 (FreeImage), and the permissive
   notices. The OCP wheel ships **none** of these; see
   [The wheel ships no licence text](#the-wheel-ships-no-licence-text-at-all).
3. **Add a `NOTICE` file** at the repo root and copy it into the images,
   naming OCCT prominently — the Open CASCADE exception _requires_ "prominent
   notice in supporting documentation."
4. **Serve corresponding source** for the two LGPL components (OCCT and
   planegcs) at pinned, durable URLs, and reference them from the image
   labels and the `NOTICE`. LGPL-2.1 §6(d) is the clause we are relying on;
   §6(b) does **not** apply to us. See [Which §6 route](#which-6-route-we-are-actually-on).
5. **Add OCI image labels** recording licence and source
   (`org.opencontainers.image.licenses`, `.source`), so the obligation
   travels with the artifact rather than living only in a README.

Conditions 2, 3 and 5 are `deploy/` and root-file work. Condition 1 is a
`deploy/` change. Condition 4 is a hosting decision plus text.

**Until condition 1 lands, do not publish a `geometry` image.** Conditions
2–5 are obligations we would be breaching; condition 1 is a policy violation
_and_ an obligation we could not meet without relicensing the image.

---

## 1. Scope — what "redistribute" changes

There are two distribution postures and they carry different duties:

| posture                                | who conveys the binaries      | obligations                    |
| -------------------------------------- | ----------------------------- | ------------------------------ |
| A user runs `uv sync` / `pip install`  | **PyPI / the wheel publisher** | essentially none fall on us    |
| We publish a container image           | **us**                        | the full §6 set, below         |

Everything that follows is about the second row. The first row is why this
never came up during development: nothing in `just dev` or `just test` makes
us a distributor. `docker push` does.

A container image is a redistribution of every byte in it. Our geometry image
would contain ~95 MB of OCCT shared libraries plus 22 vendored third-party
`.so` files that came along inside the OCP wheel.

---

## 2. OCCT — the standing position holds, with one correction

### What OCCT is licensed under

Open CASCADE Technology is **LGPL-2.1**, plus a project-specific exception.
Both texts are in the upstream repository:

- `LICENSE_LGPL_21.txt` — verbatim GNU LGPL 2.1, 502 lines.
- `OCCT_LGPL_EXCEPTION.txt` — reproduced here in full because it is short and
  it is the part people get wrong:

> Open CASCADE exception (version 1.0) to GNU LGPL version 2.1.
>
> The object code (i.e. not a source) form of a "work that uses the Library"
> can incorporate material from a header file that is part of the Library.
> As a special exception to the GNU Lesser General Public License version 2.1,
> you may distribute such object code incorporating material from header files
> provided with the Open CASCADE Technology libraries (including code of CDL
> generic classes) under terms of your choice, **provided that you give
> prominent notice in supporting documentation to this code that it makes use
> of or is based on facilities provided by the Open CASCADE Technology
> software.**

Retrieved 2026-07-31 from
`https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/master/OCCT_LGPL_EXCEPTION.txt`.

The exception solves the C++-specific problem that LGPL-2.1 §5 creates:
inline functions and templates from headers get compiled _into_ your object
code, which would otherwise make your binary a derivative work. It is a
**relaxation** granted in exchange for one concrete duty: **prominent notice
in supporting documentation.** That duty is condition 3 above, and we do not
currently discharge it — the string "Open CASCADE" appears nowhere in
`README.md`, and there is no `NOTICE` file.

### What OCP means for it

We consume OCCT through `cadquery-ocp-novtk` 7.9.3.1.1 (package name `OCP`).
Two distinct licences are stacked here and conflating them is the trap:

- The **binding code** (pybind11 wrappers, generated by pywrap) is
  **Apache-2.0**. That is what the wheel's `METADATA` declares:
  `License: Apache-2.0`.
- The **68 bundled `libTK*.so` files** are Open CASCADE Technology itself,
  **LGPL-2.1 + the exception above**. The wheel metadata says nothing about
  them.

Reproduce:

```bash
SP=$(.venv/bin/python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
grep '^License' "$SP"/cadquery_ocp_novtk-*.dist-info/METADATA   # Apache-2.0
ls "$SP"/cadquery_ocp_novtk.libs/ | grep -c '^libTK'            # 68
du -sh "$SP"/cadquery_ocp_novtk.libs/                           # 95M
```

So a naive "the wheel says Apache-2.0" scan reports this tree as fully
permissive. **It is not.** Any automated licence scan we add to CI must read
the bundled binaries, not the wheel metadata.

### The wheel ships no licence text at all

```bash
grep -iE 'licen|copying|notice' "$SP"/cadquery_ocp_novtk-*.dist-info/RECORD
# → no matches (of 398 recorded files)
```

The OCP wheel contains **zero** licence files. Neither the LGPL text nor the
OCCT exception is present. If we `COPY` the venv into an image and push it, we
convey LGPL-covered binaries with none of their required text. That is
condition 2, and it is a real breach, not a formality — LGPL-2.1 §6 says "You
must supply a copy of this License" without qualification.

(For contrast, `planegcs` does the right thing: its wheel carries
`planegcs-0.8.0.dist-info/licenses/LICENSE`, the full LGPL-2.1.)

### Which §6 route we are actually on

This is the correction to the folklore. LGPL-2.1 §6 offers five ways to
satisfy the source obligation. The one everybody assumes applies is **6(b)**:

> b) Use a suitable shared library mechanism for linking with the Library. A
> suitable mechanism is one that **(1) uses at run time a copy of the library
> already present on the user's computer system**, rather than copying library
> functions into the executable, and (2) will operate properly with a modified
> version of the library …

**Clause (1) fails for a container image.** We do not use a copy already
present on the user's system — we ship the library _in_ the image. Dynamic
linking is necessary for 6(b) but not sufficient; the library also has to be
the user's, not ours. "We link dynamically, therefore 6(b), therefore nothing
to do" is wrong for anyone shipping a container, and it is the single most
common LGPL error in container publishing.

Clause (2) we _do_ satisfy, and it is worth recording because it is the part
that makes everything else easy: both LGPL components are loaded through
ordinary shared-object mechanisms and a user can replace them.
`OCP.cpython-312-x86_64-linux-gnu.so` resolves the OCCT libraries through a
normal `DT_NEEDED` + `RPATH` lookup, and `planegcs` is a CPython extension
module imported at run time. Swapping in a rebuilt, interface-compatible
`libTKBRep.so` or a modified `planegcs` wheel works without touching our code.

So the route we take is **6(d)**:

> d) If distribution of the work is made by offering access to copy from a
> designated place, offer equivalent access to copy the above specified
> materials from the same place.

We distribute from a container registry — a designated place — so we offer
equivalent access to the corresponding source from the same place, backed by a
**6(c) written offer** as a belt-and-braces fallback. Concretely: pinned
source URLs in `NOTICE` and in the OCI `image.source` label, plus a written
offer valid three years. That is condition 4.

**Verdict on `docs/RESEARCH.md` §8's "LGPL (dynamic) ok":** the position is
**correct and stays**, but "dynamic" is not the reason it is ok, and the entry
should not be read as "and therefore nothing to do." §8 has been amended in
the same commit as this document to say so.

---

## 3. planegcs — LGPL-2.1-or-later, and it is load-bearing

`planegcs` 0.8.0 is the 2D constraint solver behind every sketch. It is
FreeCAD's PlaneGCS extracted into a standalone Python extension, and its own
`METADATA` says `License: LGPL-2.1-or-later`. FreeCAD's licence requirements
compel that, as the package README states.

The repo already treats it correctly at the architecture level — the solver
sits behind a protocol (`geometry/sketch/solver.py`) and `planegcs` types never
escape `geometry/sketch/planegcs_solver.py` — which keeps the swap cheap and
keeps the guardrail honest. Nothing about the code needs to change.

The **redistribution** duty is identical to OCCT's: convey the LGPL text
(the wheel does ship it — copy it into the image), give notice, and offer
corresponding source. No exception applies here (the OCCT exception is
OCCT's), but none is needed: we call it from Python across a C-extension
boundary and incorporate none of its headers.

---

## 4. P0 — jbigkit (GPL-2.0) is vendored inside the OCP wheel

**This is the finding that blocks the geometry image, and it is not about
OCCT.**

The OCP wheel was built with `auditwheel`, which grafts the build machine's
Ubuntu 20.04 system libraries into the wheel. 22 non-OCCT `.so` files came
along. One of them is GPL.

```bash
ls "$SP"/cadquery_ocp_novtk.libs/ | grep -v '^libTK'
# libHalf libIex libIlmImf libIlmThread libfontconfig libfreeimage libfreetype
# libgomp libjbig libjpeg libjpegxr libjxrglue liblcms2 liblzma libopenjp2
# libpng16 libraw libtiff libuuid libwebp libwebpmux libzstd
```

`libjbig` is **jbigkit** by Markus Kuhn. Its licence, from the source header
of `libjbig/jbig.c` (retrieved 2026-07-31 from the `ImageMagick/jbig` source
mirror, whose `COPYING` is the verbatim GNU GPL v2):

> This program is free software; you can redistribute it and/or modify
> it under the terms of the **GNU General Public License** as published by
> the Free Software Foundation; either **version 2** of the License, or
> (at your option) any later version.

### It is genuinely linked, not merely present

```bash
readelf -d "$SP"/cadquery_ocp_novtk.libs/libtiff-*.so.5.5.0 | grep jbig
# → NEEDED  libjbig-0f1087b4.so.0
```

The chain is `OCP.cpython-312-*.so` → `libTKService` → `libfreeimage` →
`libtiff` → `libjbig`, every hop a hard `DT_NEEDED`. And it is not theoretical
— the GPL library is mapped into the address space of any process that touches
the kernel at all:

```bash
.venv/bin/python -c "
import OCP.BRepPrimAPI
print('libjbig' in open('/proc/self/maps').read())"
# → True
```

`import OCP.BRepPrimAPI` is the first thing the geometry service does.

### Why this matters even though MIT is GPL-compatible

Two readings exist and both lead to the same operational answer:

- **"Mere aggregation"** (GPLv2 §2, final paragraph) — an image is a
  distribution medium, so bundling a GPL library beside an MIT app does not
  relicense the app. Under this reading we owe jbigkit's corresponding source
  and licence text, and nothing more.
- **"Combined work"** — the FSF's position on dynamic linking. `libjbig` is
  linked into a single process with everything else, so the combination must
  be conveyable under GPL-2.0.

MIT is GPL-compatible and LGPL-2.1 permits conversion to GPL-2 (§3), so the
second reading produces no _conflict_ — the aggregate is distributable, under
GPL-2.0 terms. But it would make **the published geometry image effectively
GPL-2.0**, which:

- contradicts what `README.md`, `LICENSE` and the image labels would say;
- contradicts our own standing rule, stated in `CLAUDE.md`, `CONTRIBUTING.md`
  and `docs/RESEARCH.md` §8: **"No GPL/AGPL dependencies."** That rule is
  absolute and has no dynamic-linking carve-out;
- drags in a corresponding-source obligation over a large binary set for a
  codec **we never call**.

We do no TIFF I/O anywhere. This is dead weight that arrived by accident of
someone else's build machine.

### The fix — verified, not proposed

Deleting `libjbig` outright does **not** work; the libraries are built with
eager binding:

```
ImportError: libtiff-688daa34.so.5.5.0: undefined symbol: jbg_enc_out
```

`libtiff` imports exactly **10** symbols from it:

```bash
nm -D --undefined-only "$SP"/cadquery_ocp_novtk.libs/libtiff-*.so.5.5.0 | grep jbg
# jbg_dec_free jbg_dec_getimage jbg_dec_getsize jbg_dec_in jbg_dec_init
# jbg_enc_free jbg_enc_init jbg_enc_out jbg_newlen jbg_strerror
```

So replace jbigkit with a GPL-free stub exporting those ten symbols, each of
which aborts if ever called. **This was built and tested on 2026-07-31**: with
the real `libjbig` replaced by a ~20-line stub compiled from our own source,
OCCT loads and produces correct geometry —

| check                        | result                                     |
| ---------------------------- | ------------------------------------------ |
| `import OCP`                 | ok                                          |
| boolean cut (box − cylinder) | **5151.77 mm³**, matching `10·20·30 − π·3²·30` analytically |
| `BRepMesh_IncrementalMesh`   | ok                                          |
| STEP export                  | 19 020 bytes, 434 entities                  |

The stub belongs in `deploy/docker/service.Dockerfile` (platform-builder's
territory — filed in `docs/BACKLOG.md` as **LIC-1**), applied after `uv sync`,
with a build-time assertion that no GPL-licensed `.so` remains in the image.

**Alternatives considered:** rebuilding libtiff without JBIG support
(`--disable-jbig`) is cleaner and equally valid, at the cost of a compiler in
the image build; building OCCT without FreeImage (`-DUSE_FREEIMAGE=OFF`)
removes the whole `libfreeimage → libtiff → libjbig` subtree and is the
_correct_ long-term answer, at the cost of maintaining our own OCP wheel.
The stub is the cheapest thing that makes the images publishable now; a
follow-up should ask the OCP maintainers to drop the JBIG codec upstream,
which fixes it for everyone downstream of that wheel.

---

## 5. The rest of the tree — full sweep

Method (re-runnable):

```bash
.venv/bin/python -c "
from importlib.metadata import distributions
for d in distributions():
    m = d.metadata
    print(m.get('Name'), m.get('License-Expression') or m.get('License') or
          [c for c in m.get_all('Classifier') or [] if c.startswith('License')])"
uv tree --package loft-geometry --no-dev     # and gateway / documents
pnpm licenses list --prod
```

### Python — the only copyleft is in the geometry closure

`uv tree --no-dev` gives 82 runtime packages for geometry, 36 for gateway,
27 for documents.

| component                          | licence                          | where            | duty |
| ---------------------------------- | -------------------------------- | ---------------- | ---- |
| OCCT 7.9.3 (68 `libTK*.so`)        | LGPL-2.1 + OCCT exception        | geometry         | text + notice + source offer |
| `planegcs` 0.8.0                   | LGPL-2.1-or-later                | geometry         | text + notice + source offer |
| **`libjbig` (jbigkit)**            | **GPL-2.0-or-later**             | geometry         | **remove — P0** |
| `libfreeimage` 3.18                | FIPL-1.0 **or** GPLv2 **or** GPLv3 | geometry       | elect **FIPL-1.0**; ship its text |
| `libraw` 0.19                      | LGPL-2.1 **or** CDDL-1.0         | geometry         | elect LGPL-2.1; text + offer |
| `libgomp`, `libgfortran`, `libquadmath` | GPL-3 **WITH** GCC-Runtime-Library-Exception | geometry | none beyond notice — the exception exists precisely for this |
| `libfreetype`                      | FTL **or** GPLv2                 | geometry         | elect **FTL**; ship its text |
| `certifi`                          | MPL-2.0                          | geometry         | file-level copyleft; ship text, note source location |
| everything else                    | MIT / BSD / Apache-2.0 / ISC / PSF / MIT-CMU / 0BSD / Unlicense | all | attribution only |

Notes worth recording:

- **`libgomp` / `libgfortran` are not a problem.** They are GPL-3 _with the
  GCC Runtime Library Exception_, which explicitly permits redistribution
  inside non-GPL software. This is the one place where "GPL" in a scan result
  is genuinely fine, and it is why a scanner that greps for the string GPL
  will produce false alarms here. Do not "fix" them.
- **Dual-licensed components require us to elect, and to say so.** FreeImage,
  LibRaw, FreeType and zstd all offer a permissive-or-GPL choice; silence is
  not an election. `NOTICE` must state which arm we take.
- **Pillow's bundled `libtiff` 6.2.0 carries no `libjbig`** — only OCP's
  Ubuntu-20.04-era `libtiff` 5.5.0 does. The P0 is specific to that wheel.
- **`gateway` and `documents` closures contain no copyleft whatsoever** —
  verified by inspection of both `uv tree` outputs. Those two images are clean
  today.

### JavaScript — clean

`pnpm licenses list --prod` over 78 production packages:

| licence      | count |
| ------------ | ----- |
| MIT          | 66    |
| Apache-2.0   | 5     |
| ISC          | 3     |
| OFL-1.1      | 2     |
| BSD-3-Clause | 1     |
| Unlicense    | 1     |

**No GPL, no AGPL, no LGPL, no MPL.** The two OFL-1.1 entries are the
self-hosted fonts (`@fontsource/hanken-grotesk`, `@fontsource/fragment-mono`);
OFL requires the copyright notice and licence to travel with the font files,
which they do inside the packages, plus a `NOTICE` mention. The Reserved Font
Name clause also means we must not ship a _modified_ font under the same name
— we do not modify them.

### No AGPL anywhere

Checked across both ecosystems. Zero AGPL components. The one thing to keep
watching is that AGPL is common in the adjacent tooling space (some
visualization and collaboration servers), so the review rule stays.

---

## 6. Compliance checklist

Executable, in the order it should be done.

### In every image

- [ ] `/app/licenses/LICENSE` — our MIT licence.
- [ ] `/app/licenses/NOTICE` — the root `NOTICE`, verbatim.
- [ ] `/app/licenses/THIRD-PARTY.md` — generated inventory (name, version,
      licence, source URL) for that image's closure.

### In the geometry image only

- [ ] jbigkit removed (condition 1); build fails if `libjbig` with GPL
      symbols survives.
- [ ] `/app/licenses/LGPL-2.1.txt` — full text, covers OCCT, planegcs, LibRaw.
- [ ] `/app/licenses/OCCT_LGPL_EXCEPTION.txt` — the exception text.
- [ ] `/app/licenses/FreeImage-FIPL-1.0.txt`, `FTL.txt`, `MPL-2.0.txt`.
- [ ] `/app/licenses/CORRESPONDING-SOURCE.md` — the 6(d) access statement and
      the 6(c) written offer, with pinned URLs and the exact upstream versions
      (OCCT **7.9.3**, planegcs **0.8.0**).

### In `NOTICE` (repo root)

- [ ] The OCCT prominent-notice sentence, worded to satisfy the exception:
      _"This software makes use of facilities provided by the Open CASCADE
      Technology software."_
- [ ] planegcs / FreeCAD PlaneGCS attribution.
- [ ] The dual-licence elections (FreeImage → FIPL-1.0, LibRaw → LGPL-2.1,
      FreeType → FTL).
- [ ] Font attribution (OFL-1.1, both families).
- [ ] Where corresponding source is served.

### On the image (OCI labels)

- [ ] `org.opencontainers.image.licenses` — `MIT AND LGPL-2.1-or-later` for
      geometry; `MIT` for gateway and documents.
- [ ] `org.opencontainers.image.source` — the repo URL.
- [ ] `org.opencontainers.image.documentation` — link to this file.

### In `README.md`

- [ ] A licensing paragraph stating that the geometry image bundles
      LGPL-2.1 components, naming OCCT, and linking here. (Done — see the
      "License & attribution" section.)

### Ongoing

- [ ] A CI job that fails on any new GPL/AGPL component **and reads bundled
      binaries, not just wheel metadata** — the OCP wheel proves metadata
      scanning is insufficient (it declares Apache-2.0 while carrying GPL-2.0).
- [ ] Re-run this analysis on any OCP/OCCT version bump; the vendored set is
      a property of the wheel's build machine and can change without notice.

---

## 7. Where corresponding source comes from

For LGPL-2.1 §6(d)/(c), the materials must be the **exact** versions shipped.

| component | version   | upstream |
| --------- | --------- | -------- |
| OCCT      | 7.9.3     | `https://github.com/Open-Cascade-SAS/OCCT` (tag `V7_9_3`) |
| planegcs  | 0.8.0     | `https://github.com/spookylukey/planegcs` |
| LibRaw    | 0.19.5    | Ubuntu 20.04 source package `libraw` |
| FreeImage | 3.18.0    | Ubuntu 20.04 source package `libfreeimage` |
| FreeType  | 2.10.1    | Ubuntu 20.04 source package `freetype` |

"Offer equivalent access from the same place" is cleanest to satisfy by
attaching a source bundle to the same release the images are published under,
rather than pointing at a third party who may retire a URL. A link to upstream
alone is the weakest defensible reading of 6(d); a mirrored archive under our
own release is the strong one. **Recommend mirroring.**

---

## 8. What this changes elsewhere

- `docs/RESEARCH.md` §8 — amended in the same commit: the allow-list stands,
  but "LGPL (dynamic) ok" now records that the dynamic-linking property
  satisfies §6(b)(2) only, that §6(b)(1) fails for container images, and that
  redistribution therefore carries §6(d) duties.
- `docs/BACKLOG.md` — **LIC-1** (strip jbigkit, P0) and **LIC-2** (licence
  files, `NOTICE`, labels, source mirror) filed for platform-builder.
- `NOTICE` — created at the repo root in this commit.

---

## 9. LIC-1 / LIC-3 as shipped — platform-builder, 2026-07-31

Appended, not a rewrite: §§1–8 above are the analysis, this is what was built
from it and what was measured. Only §4's fix and §6's checklist are affected.

### What the geometry image now contains, and does not

`libjbig-0f1087b4.so.0` is still **present**, with the same file name and the
same `SONAME` — and it is a **16 KB GPL-free stub compiled from
`deploy/docker/licence/jbig-stub.c`**, original MIT work containing no jbigkit
code, exporting exactly the ten `jbg_*` symbols `libtiff` imports and aborting
loudly if any is ever called. jbigkit's 62 KB of GPL-2.0 object code, and both
copies of its `"JBIG-KIT 2.1 ... Licence: GPL"` string, are gone.

Replacing rather than deleting is not a stylistic choice: the vendored
libraries use eager binding, so a deleted `libjbig` gives
`ImportError: libtiff-*.so.5.5.0: undefined symbol: jbg_enc_out` at the first
`import OCP`. The gate below fails on that too, by name.

The image also now carries `/app/licenses/` — our `LICENSE`, the root `NOTICE`,
the five texts no wheel ships (`LGPL-2.1.txt`, `OCCT_LGPL_EXCEPTION.txt`,
`FTL.txt`, `FreeImage-FIPL-1.0.txt`, `MPL-2.0.txt`),
`CORRESPONDING-SOURCE.md` (the §6(d) statement and the §6(c) written offer),
plus a generated `THIRD-PARTY.md` and every licence file the wheels themselves
ship, copied out of the installed environment at build time — and the OCI
labels `image.licenses` / `.source` / `.documentation` / `.title`.

### The assertions that would fail on a regression

All three fail the **build**, so a silent re-introduction is not possible:

| assertion | fails when |
| --------- | ---------- |
| `strip-gpl-jbig.sh … --require` | no `libjbig` is found at all (a skipped strip cannot pass as a clean build), the file is neither jbigkit nor our stub, the marker is missing after the write, a GPL string survives, or any of the ten symbols is not exported |
| `check-licences.py --profile image` | any GPL-family library is present; a `strip-in-image` entry is present **and is not the stub**; it was deleted and an importer still needs `jbg_*`; the stub fails to define a symbol its importer imports; a new vendored library is unclassified; a Python distribution declares GPL/AGPL; the `image.licenses` label disagrees with the contents in **either** direction |
| `verify-kernel.py` | the mapped `libjbig` in `/proc/self/maps` is not the stub; the boolean cut misses the closed-form volume by >1e-6 mm³; tessellation or STEP export fails |

The wording a regression produces, verbatim:

> `libjbig-0f1087b4.so.0: GPL-2.0-or-later library 'libjbig' is present in an
> image about to be published, and it is NOT our GPL-free replacement (marker
> 'LOFT-GPL-FREE-JBIG-STUB' absent). deploy/docker/licence/strip-gpl-jbig.sh
> did not run, or ran and did not take. This is a licence violation, not a
> warning.**

### Proof the geometry is unchanged

Measured by loading the stub ahead of the real library through `LD_LIBRARY_PATH`
(`libtiff` uses `RUNPATH`, which `LD_LIBRARY_PATH` precedes, so the GPL library
is never mapped — confirmed in `/proc/self/maps`), then running the real suites:

| check | result |
| ----- | ------ |
| boolean cut (10×20×30 box − ⌀6×30 cylinder) | **5151.769984 mm³**, equal to `10·20·30 − π·3²·30` to 1e-6 |
| `test_goldens.py` + `test_assembly_goldens.py` | **210 passed** |
| whole `services/geometry/tests` suite | **2385 passed, 1 skipped** |
| tessellation + STEP export | 19 020 bytes, 434 entities — byte-identical to §4's numbers |

Goldens assert stored content hashes, so "passed" here means byte-identical
output, not merely "close". The codec is unreachable, as §4 predicted.

### Where the gate runs

- `just lint` and the CI `licences` job — `--profile source-env` over the
  uv-synced environment. No daemon needed.
- CI `licences` job — `--self-test`: the **image** profile against the real,
  unstripped GPL library (must fail, naming `libjbig`), then the production
  strip script, then again (must pass). A gate that quietly stopped detecting
  anything cannot show green.
- The image build itself, and again against the finished image in
  `deploy-path`, which prints the mapped-stub path, the measured volume and the
  labels rather than inferring them.

### Corrections to the numbers above

- §2 and §5 say the wheel bundles "68 `libTK*.so` files". The wheel's
  `cadquery_ocp_novtk.libs/` contains **68 files in total**, of which **46** are
  `libTK*` (OCCT) and 22 are the non-OCCT set §4 lists. The reproduce command
  in §2 counts the directory, not the pattern. The argument is unaffected.
- §5's per-image totals are unchanged, but for the record the full environment
  carries **96** loose shared libraries once `pillow`/`scipy`/`numpy`/
  `scikit-learn`/`lib3mf` are counted; all are classified in
  `scripts/check-licences.py`.
- The file ended with a stray `</content>` tag from the tool that wrote it;
  removed here.

### Still open (LIC-2)

The mirrored corresponding-source bundle attached to the release — §7's
"recommend mirroring" — is not done. `CORRESPONDING-SOURCE.md` says so
explicitly rather than implying coverage we do not have.
