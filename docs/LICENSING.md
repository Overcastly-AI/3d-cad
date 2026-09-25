# Licensing

> **This is an engineering analysis, not legal advice.** Each claim can be
> re-checked against the licence text or a command in this repo. Before a
> commercial redistribution decision, have a lawyer read it. The full
> measured analysis this summarises is in git:
> `git show 5b6fd28:docs/LICENSING.md`.

## Status

Loft is MIT. The gateway and documents images contain only permissive code.
The geometry image bundles LGPL components (OCCT, planegcs, LibRaw) and meets
the obligations listed in §6. **No workflow publishes images;** publishing is
the founder's decision, and §7 is the procedure.

## 1. Scope

Installing dependencies (`uv sync`, `pip install`) makes the wheel publisher
the distributor, and puts almost no duty on us. **Publishing a container
image makes us the distributor of every byte in it**, and brings the
duties below.

## 2. OCCT: LGPL-2.1 with the Open CASCADE exception

This is allowed from an MIT app, but dynamic linking is not the reason. LGPL
§6(b) requires a copy of the library that is "already present on the user's
computer system", and that fails for an image we ship. We rely on **§6(d)**,
equivalent access to source from the same place, backed by a §6(c) written
offer. The exception also requires a prominent notice (the root `NOTICE`
provides it). Users can still swap in a modified library (§6(b)(2)), because
OCP resolves OCCT through ordinary `DT_NEEDED` and `RPATH` lookup.

## 3. planegcs: LGPL-2.1-or-later

This is the sketch solver, kept behind the `SketchSolver` protocol. It has the
same duties as OCCT (licence text, notice, source) and no exception is needed.

## 4. jbigkit (GPL-2.0) inside the OCP wheel

The OCP wheel declares Apache-2.0 but vendors 22 system libraries, one of them
GPL-2.0 `libjbig`, hard-linked through `libtiff`. Deleting it breaks loading,
so the geometry image replaces it with a stub
(`deploy/docker/licence/jbig-stub.c`, `strip-gpl-jbig.sh`) that exports the
ten symbols `libtiff` needs and aborts if any is called. Loft does no TIFF or
JBIG I/O. `deploy/docker/licence/verify-kernel.py` proves the kernel still
builds correct geometry. **The lesson for every dependency is that metadata
cannot be trusted, so `scripts/check-licences.py` (in `just lint` and CI)
reads the binaries.**

## 5. The rest of the tree

There are no GPL or AGPL dependencies in either the Python or the JS closure.
The remaining copyleft is LGPL (above), MPL-2.0 (certifi, pure Python, so the
source ships) and dual-licensed libraries where we elect the permissive arm
(FreeImage FIPL-1.0, FreeType FTL, LibRaw LGPL-2.1). The fonts are OFL-1.1 and
unmodified.

**MinIO is AGPL-3.0.** The compose stack runs it as a separate S3 server over
the network. No Loft code links or bundles it, and any S3 store can replace it
through `S3_URL`. `deploy/docker/minio.Dockerfile` builds it unmodified from
pinned source and carries its licences and source labels. Publishing that
image would bring AGPL §6 duties. Whether to keep MinIO at all is an open
founder decision (`docs/BACKLOG.md`).

## 6. Compliance checklist (as shipped)

- **Every image:** `/app/licenses/` with our `LICENSE`, the root `NOTICE` and
  a third-party inventory; OCI labels `org.opencontainers.image.licenses`
  (`MIT AND LGPL-2.1-or-later` for geometry, `MIT` otherwise), `.source` and
  `.documentation`.
- **Geometry image:** jbigkit stubbed (the build fails if GPL symbols
  survive), the LGPL-2.1 text, the OCCT exception, FIPL, FTL, MPL-2.0, and
  `CORRESPONDING-SOURCE.md` (the §6(d) statement and the §6(c) offer).
- **`NOTICE`:** the OCCT prominent notice, planegcs attribution, the
  dual-licence elections, font attribution, and where the source is served.
- **Ongoing:** `check-licences.py` fails on any new GPL/AGPL binary and on any
  version drift from `deploy/licenses/corresponding-source.json`. Re-read §4
  on every OCP/OCCT bump.

## 7. Corresponding source

The exact shipped versions are pinned in
`deploy/licenses/corresponding-source.json`, and every `just lint` and CI run
checks them against the installed binaries.

### 7.1 What carries a source obligation

| Component | Version           | Licence                   | Source                                                                    |
| --------- | ----------------- | ------------------------- | ------------------------------------------------------------------------- |
| OCCT      | 7.9.3             | LGPL-2.1 + OCCT exception | `github.com/Open-Cascade-SAS/OCCT`, tag `V7_9_3`, commit `a016080`        |
| planegcs  | 0.8.0             | LGPL-2.1-or-later         | PyPI sdist `planegcs-0.8.0.tar.gz`                                        |
| LibRaw    | 0.19.5-1ubuntu1.4 | LGPL-2.1 (our election)   | Ubuntu 20.04 source package (`.orig` + `.debian` + `.dsc`, with patches) |

FreeImage and FreeType have no source obligation, because we elect their
permissive licences.

### 7.2 Fetch it

```sh
just corresponding-source v0.1.0   # writes dist/corresponding-source/
```

The script checks the pinned versions against `.venv`, fetches each artefact
and verifies its SHA-256, clones OCCT at the pinned commit and packs it
reproducibly, and assembles one tarball with a manifest and `SHA256SUMS`. If
anything fails, it writes no bundle.

### 7.3 Publish it (the founder's step)

```sh
gh release upload <tag> dist/corresponding-source/loft-corresponding-source-<tag>.tar.gz --clobber
```

Attach it to the same release that publishes the images, then check that
the offer inside the image points at an asset that exists and verifies.

### 7.4 When a wheel bump moves a version

`check-licences.py` fails with the old and new version. To clear it:

1. Re-derive the upstream identity.
2. Update `corresponding-source.json`, nulling the old digests.
3. Run `just corresponding-source-record <tag>` and read the diff.
4. Re-check §4 for newly vendored libraries.

`just licence-selftest` proves the gate can still fail.

### 7.5 GCC runtime libraries

`libgomp`, `libgfortran` and `libquadmath` are GPL-3.0 with the GCC Runtime
Library Exception. They are present only because compiled extension modules
need them. The exception covers conveying them combined with those modules,
so we mirror no source for them. Publishing one on its own would change that.
`check-licences.py` fails on any runtime library whose build-id is not
recorded in the `gcc_runtime` block of `corresponding-source.json`, and
`deploy/licenses/CORRESPONDING-SOURCE.md` has the per-file table.

## 10. As shipped

LIC-1 (the jbigkit stub), LIC-2 (licence files, `NOTICE`, labels and the
source-bundle tooling, with digests computed from real downloads), LIC-3 (the
binary licence gate) and LIC-4 (the GCC runtime decision) are all done. The
measurements are in the git history of this file.
