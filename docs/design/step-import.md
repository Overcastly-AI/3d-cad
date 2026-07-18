# STEP Import — Representation & Storage in the Feature Tree — Design

Status: **BACKEND IMPLEMENTED (v1 inline)** 2026-07-13 — the geometry-side
import (`ImportFeature` base feature, kernel `STEPControl_Reader` path, golden
round-trip proof) plus this decision. The gateway upload endpoint, documents
blob handling, and the in-viewport "open a STEP" UI are the named follow-ups
(§8). Flips the VISION scorecard **Interop** row from ❌ toward ➖: export
already round-trips exact (STEP out → reopened at identical volume), so the row
was gated purely on import — an external part can now come IN and be modeled on
(fillet/cut/sketch-on-face, since the topological-naming face/edge machinery
already works on any body).

Read first (the machinery this reuses): [`feature-tree.md`](./feature-tree.md)
§1.3–1.4 (versioned param envelopes + upcast registry), §4 (the
documents→geometry evaluation contract, strict-prefix rule), §7.6 (single body
chain), §7.8 (the object-storage successor to the interim content-addressed
seam); [`datum-planes.md`](./datum-planes.md) (the "seed a `kind`/`format`
discriminator for a named additive future" idiom this follows);
[`topological-naming.md`](./topological-naming.md) (the face/edge signatures that
already resolve against *any* body — including an imported one); RESEARCH §5
(content-addressed mesh security constraint — the tenancy flag in §6), §9
(determinism + golden gates).

The hard question this doc settles: **how imported geometry is represented and
stored in the feature tree so a part re-evaluates deterministically** — and,
because a STEP file is untrusted external input, how parse failures and
oversize payloads stay legible (never a 500; the parse is hard-bounded in
wall-clock time by a killable subprocess, see §6). The kernel read itself
is easy (OCCT already reads STEP — the export round-trip uses it); the design
weight is on the *contract*.

---

## 1. Decision 1 — import is a BASE feature that PRODUCES the body

An `ImportFeature` (`type: "import"`, `version: 1`) is a **body-affecting base
feature**: like the first extrude, it does not modify a prior body — it **sets**
the part's single solid body chain (§7.6) to the imported solid. Every later
feature (fillet, chamfer, extrude-cut, shell, an `on_face` datum / picked-edge
selector) then operates on that body exactly as it would on a modeled one; no
new machinery is needed downstream, which is the whole point.

- **Why a feature, not a side channel.** Everything in a part is a tree node
  (datum-planes §2b): inspectable, renameable, reorderable, deletable,
  roll-back-past, and — decisively — **re-evaluated deterministically from its
  params** every rebuild. An import that lived outside the tree would be a
  second, parallel source of body state; an import *feature* rides the existing
  evaluate contract verbatim (§4.3 strict-prefix, the `no_prior_body` family,
  the last-good-body tessellation).
- **v1 is the FIRST body (no prior body).** Because v1 has no `add`/`cut`
  operation param and no multi-body support (§7.6), an import is only valid when
  **no body precedes it**. An import with a prior body is an honest per-feature
  `import_with_prior_body` error — combining an imported solid with an existing
  body (a positioned "insert derived part", multi-body assemblies) is future
  work, named not built (§7). Import-first covers the entire target flow:
  *open an external part, then fillet / cut / sketch on its faces.*
- **Independent of topological naming (#1).** The import carries no `FeatureRef`
  / `SubshapeRef` — its geometry comes wholly from its own params, so it
  materializes **no** `feature_dependencies` edge (like an offset datum or a
  pattern). It is, however, added to `BODY_AFFECTING_FEATURE_TYPES`, so a later
  `SubshapeRef` may name a **face or edge of the imported body** — "sketch on
  the face of an imported part" works for free.

---

## 2. Decision 2 — v1 payload representation: STEP text INLINE in the params

Two ways to get the STEP bytes to the stateless geometry service:

### 2a. Content-addressed BLOB reference (chosen for v2, not v1)

The STEP is stored once in object storage / a documents blob table and the
feature params carry a `sha256:` reference. Cleaner for large parts (the
feature-tree JSON stays small), ties naturally to the §7.8 object-storage
successor, and dedups identical uploads.

- **Against, for v1:** it forces a **new storage dependency now** — a blob
  bucket/table, an upload endpoint that writes it, a lifecycle (orphan GC when
  the feature is deleted), and a tenancy decision (§6). None of that exists
  yet (this container runs no MinIO; the mesh store is an interim in-process LRU
  — mesh_store.py / §7.8). Building it as a prerequisite to *any* import inverts
  the delivery order.

### 2b. STEP text INLINE in the feature params (chosen for v1)

`ImportParamsV1` carries the STEP AP214 part-21 **text inline** as a bounded
string (`data`). The feature is fully self-contained: the evaluate request that
crosses the documents→geometry boundary already carries the params, so the
geometry service needs **no** storage, no new endpoint, no lifecycle — it reads
the bytes straight from the DTO. Storage is the feature tree's existing JSONB
(documents/Postgres), which is **already tenant-scoped** (§6).

- **For:** cleanest possible v1 — self-contained, no new infrastructure,
  deterministic by construction (the bytes are pinned in the tree), and it
  dogfoods the boundary (the golden's `model.json` literally carries the STEP
  text, proving the representation end-to-end).
- **Tradeoff, stated honestly:** a real mechanical part's STEP is tens of KB to
  a few MB; inlining it puts a large blob in the feature-tree JSON and in every
  evaluate request. That is acceptable at v1 part sizes and bounded hard (§6),
  but it does **not** scale to large assemblies and it re-ships the bytes on
  every rebuild. This is the reason 2a exists.

### Migration path 2b → 2a (additive, no `param_version` bump)

`ImportParamsV1` seeds a **`kind` source discriminator** (`kind: "inline"`),
exactly the RevolveAxis / DatumParams idiom. When object storage lands (§7.8),
a `BlobStepSource` (`kind: "blob"`, `blob_ref: "sha256:…"`) joins as an additive
union member and `ImportParams` becomes
`Annotated[InlineStepSource | BlobStepSource, discriminator="kind"]` — persisted
`inline` rows validate byte-identically, so **no `param_version` bump and no
data migration**. A one-shot upgrade can *optionally* move large inline blobs to
the blob store, but is not required for correctness. The wire contract is
forward-compatible from day one.

---

## 3. Decision 3 — determinism (RESEARCH §9): pin the read

Same STEP bytes must produce a **byte-identical body/mesh across rebuilds and
interpreter restarts**. OCCT's STEP read is a pure function of the file bytes
plus the process-global `Interface_Static` settings — the latter is the only
nondeterminism risk (ambient settings a prior read in the process may have
changed). v1 **pins the settings on every import** so the result is independent
of process history:

- `Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")` — the target unit,
  pinned to millimetres (the kernel's fixed unit, RESEARCH §9 / geometry
  schemas). The exported STEP declares SI-millimetre, so this is lossless, but
  pinning it makes the scale independent of ambient config.
- Read precision stays at the OCCT file-default mode (deterministic given fixed
  bytes); v1 does not touch it. Documented so a future change is a reviewed one.

v1 reads via a dedicated `STEPControl_Reader` (`ReadFile` → `TransferRoots` →
`OneShape`), **not** build123d's `import_step`. Two reasons: (a) `import_step`
reads from a file **path only** (it `os.path.exists`-checks its argument), so
inline bytes would need a tempfile anyway; (b) it runs the heavier XCAF
color/name/assembly path (hash-keyed color caches, label traversal) we do not
need and do not want in the determinism-critical path. The low-level reader is
the same OCCT engine the export round-trip already exercises.

**Evidence (measured 2026-07-13, build123d 0.11.1 / OCCT 7.9):** a 10×20×30 box
exported to STEP then imported through this path measures **exactly** vol 6000.0,
area 2200.0, bbox `[0,0,0]..[10,20,30]`, topology 6/12/1 — **0.0 deviation** vs
the analytic box on every mass property, bbox bound, and topology count. The
re-exported STEP of the imported solid is **byte-identical across two
independent interpreter runs** (same sha256). This is the same lossless-planar
result `test_step_roundtrip` records for export; import is proven to be its
inverse.

---

## 4. Decision 4 — healing report scope: v1 is "single solid or legible error"

OCCT STEP read can yield a single solid, a compound of several solids, open
shells, or non-solid geometry (surfaces/wireframe). v1 accepts **exactly one
solid** and otherwise fails with a **legible, stats-bearing** per-feature error
— it does **not** sew/heal/repair:

- **Exactly one `TopAbs_SOLID`** in the transferred shape → wrap it as the body
  (`ok`).
- **Zero, or more than one, solids** → `import_not_single_solid`, whose message
  carries the honest shape stats — *how many* solids/shells/faces were found and
  whether a closed shell exists. That message **is** the v1 "healing report":
  the shape's composition, surfaced honestly, so a user learns *why* their file
  was rejected (e.g. "found 2 solids — multi-solid assemblies are not supported
  yet" or "found 0 solids, 3 open shells — surface/wireframe STEP is not a
  solid"). Verified: a compound of two disjoint boxes reads as a
  `TopAbs_COMPOUND` with 2 solids → rejected with that count.
- **Deferred, named not built:** IGES import; multi-solid → assembly / multi-body
  parts; sewing open shells into a solid; surface repair / small-face removal;
  a structured healing-report DTO across the boundary. Each is an additive
  follow-up (a new `format` literal, a new error/report shape) that does not
  reshape v1's params.

The mass-properties/topology of the accepted body flow out through the standard
`EvaluateTreeResult.properties` — when import is the last feature, those numbers
*are* the imported part's stats, so the "what did I get" report is already in
the evaluate response with no new DTO.

---

## 5. Error paths + evaluation semantics (§4.3 — never a 500; parse-time bounded §6)

All import failures are **per-feature `FeatureError` values inside a 200**
(strict-prefix rule) — the py-kit error envelope stays reserved for
transport/validation failures of the call itself (§4.3). The handler catches
every OCCT failure mode and maps it; a handler bug is still caught by the
dispatcher's belt-and-braces `evaluation_failed` (never a tree-wide 500).

| Situation | Surface | Code |
|---|---|---|
| STEP text OCCT cannot parse (`ReadFile` ≠ `RetDone`, or a transfer raise) | per-feature error, 200 | `import_parse_failed` |
| Parse exceeds the wall-clock bound → killable subprocess SIGKILLed (§6) | per-feature error, 200 | `import_parse_timeout` |
| Parsed but not exactly one solid (0, or ≥2; open shells; surfaces only) | per-feature error, 200 | `import_not_single_solid` |
| Import with a body already present in the prefix | per-feature error, 200 | `import_with_prior_body` |
| `data` empty or over the size bound (§6) | **request-validation 422** | pydantic `validation_error` |

Verified failure modes: garbage bytes and empty input both return OCCT
`IFSelect_RetFail` → `import_parse_failed`; neither raises nor hangs.

---

## 6. Boundary & security (untrusted input)

- **Size bound = a request-validation 422, the strongest guard.** `data` carries
  `min_length=1` and `max_length=MAX_INLINE_STEP_CHARS`
  (`packages/py_kit/schemas/features.py`), so an oversize payload is rejected by
  pydantic **before** documents stores it and **before** OCCT ever parses it —
  the DoS bound sits at the earliest possible point. This is deliberately a 422,
  not a per-feature rebuild error (the same posture as `allow_inf_nan=False` on
  a datum offset): bounding untrusted input is a validation concern, not a
  geometry outcome. The v1 ceiling is a documented, tunable balance between "real
  parts fit inline" and "JSONB / request size / parse-time DoS"; option 2a
  removes the ceiling from the tree entirely.
- **OCCT parse failures are values, never crashes.** §5 — every read error maps
  to `import_parse_failed`; the reader is wrapped so no OCCT raise escapes as a
  500.
- **Hard wall-clock bound on the untrusted parse — SHIPPED (2026-07-13, P1
  fast-follow).** The 16 MiB size cap is a request-validation 422 *before* OCCT
  parses, so it bounds the payload's **memory** footprint — but OCCT's STEP
  transfer is not guaranteed linear in input size, so an adversarial or
  degenerate part-21 can be super-linear and bound only in **time**. The two
  unbounded-time OCCT calls (`ReadFile` → `TransferRoots`) therefore run in a
  **separate, killable subprocess** (`geometry.kernel._step_parse_worker`,
  invoked by file path so it imports OCP alone — ~0.9 s cold — not the whole
  kernel), spawned with `subprocess.run(..., timeout=…)`. A parse that exceeds
  the bound is **SIGKILLed and reaped** (`subprocess.run` kills then waits before
  re-raising) and surfaces as the per-feature `import_parse_timeout` error inside
  a 200 (strict-prefix rule) — never a hang, a 500, or a leaked/zombie process.
  A thread / `signal.alarm` bound would NOT work here: it cannot interrupt OCCT
  C++ mid-transfer and signals do not fire in FastAPI threadpool threads, so the
  bound has to be a real out-of-process kill.
  - **Configurable.** `GeometrySettings.step_import_timeout_seconds` (env
    `STEP_IMPORT_TIMEOUT_SECONDS`), **default 5.0 s** — comfortably clears a real
    mechanical part's transfer while capping an adversarial one. The evaluate
    handler passes it into `import_step_solid(..., timeout_s=…)`; the kernel
    never hardcodes the value in the hot path.
  - **Determinism unaffected (strengthened, even).** Units are pinned to mm in
    the worker's FRESH process, so the read is independent of any ambient
    `Interface_Static` state; the transferred shape crosses the process boundary
    as a lossless BREP and the null / single-solid taxonomy stays in the parent.
    The `import-step-box-10x20x30` golden still measures **0.0 deviation**
    end-to-end through this subprocess path.
  - **Residual (accepted).** The bound is on *time*, not memory: a payload up to
    the 16 MiB cap can still allocate proportionally during the parse (now in the
    child process, so a kill also reclaims that memory). Per-call subprocess
    spawn adds ~0.9 s to an import feature's rebuild — well inside the 2 s
    tessellation tripwire (docs/GEOMETRY-QA.md Gate 4) and confined to the import
    path. A blob-backed source (§2a) that avoids re-shipping/re-parsing bytes on
    every rebuild is the follow-up that removes the repeated cost.
- **Boundary hygiene.** `ImportParamsV1` is pure pydantic (two string literals +
  a bounded string). No kernel type crosses the boundary: the imported
  `build123d.Solid` lives only inside geometry evaluation state (like every
  other `state.body`), never serialized. Documents stores/relays the params and
  imports **no** kernel code.
- **Tenancy flag (RESEARCH §5) — surfaced for the 2a migration.** In v1 the STEP
  lives **inline in the feature tree** (documents/Postgres), which is
  **already tenant-scoped** by the part's ownership — so no new tenancy question
  arises. **This changes under option 2a.** A raw uploaded STEP **is
  tenant-sensitive** (it is a user's proprietary CAD, unlike a derived mesh
  whose bytes are a pure function of public geometry params). The content-
  addressed mesh store is auth-gated-but-**not**-tenant-scoped *precisely because*
  a content hash is unguessable without having produced the geometry (RESEARCH
  §5). **A blob-backed STEP MUST NOT reuse that pattern** — it needs per-owner
  scoping (the blob is authored, not derived; two tenants uploading the same
  part must not share/leak it, and existence itself is sensitive). This is the
  one architecture decision 2a forces and is called out here so it is designed,
  not defaulted, when object storage lands.

---

## 7. The v1 / v2 line — deferred, named not designed

**v1 (this design):** a single-solid STEP, inline, set as the part's first body,
pinned-deterministic, single-solid-or-legible-error. Nothing picked, no prior
body, no repair.

**v2+ (each an additive increment of the *same* `import` feature — a new source
`kind`, `format` literal, or error/report shape, no `param_version` bump):**
blob-ref source (2a) + upload endpoint + per-owner tenancy (§6); IGES (a
`format: "iges"` literal); multi-solid → multi-body / assembly; sew-open-shells
and a structured healing-report DTO; positioned insert (`add`/`cut` an imported
solid against an existing body). The rule: **anything that needs new storage, a
second body, or geometry repair is v2.**

---

## 8. Follow-ups (this slice is geometry-side only)

- **Gateway upload endpoint** — accept a STEP file upload, size-bounded, and
  create an `import` feature on the part (the endpoint the UI calls). It maps a
  multipart upload to `ImportParamsV1.data`.
- **Documents** — no schema change for v1 (the params ride existing feature
  JSONB); the blob table is the 2a follow-up.
- **UI** — an "Open / Import STEP" affordance that uploads the file and appends
  the import feature, then drops the user into modeling on the imported body.

The DTO shape the upload endpoint + UI build against:

```jsonc
{ "type": "import", "version": 1,
  "params": { "kind": "inline", "format": "step", "data": "ISO-10303-21;\n…" } }
```

---

## 9. Golden (DoD — new capability ⇒ new golden, same commit)

`goldens/import-step-box-10x20x30` is a **round-trip proof**: its `data` is the
committed STEP export of the 10×20×30 box (byte-deterministic, pinned
timestamp), imported by the `import` feature; `expected.json` asserts the
**identical** analytic mass properties + topology as the `box-10x20x30` primitive
golden (vol 6000, area 2200, 6/12/1, bbox exact) within the standing planar 1e-7
bound (measured 0.0 deviation). This proves *import ≡ the inverse of export* and,
through the shared golden runner, byte-determinism in-process **and across an
interpreter restart** for free. Adding it required zero runner changes
(`geometry.harness` dispatches any `EvaluateTreeRequest`).
