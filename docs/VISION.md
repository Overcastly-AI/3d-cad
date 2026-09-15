# Vision (North Star)

> This is the *why* and *where we're going*. The **how/when** lives in
> `docs/ROADMAP.md`; the **next actions** live in `docs/BACKLOG.md`. This file is
> owned by the **vision-steward** agent: the founder dreams in plain language,
> the steward formalizes ideas here and hands them to the build loop.

## Working name

**Loft** (working title — a CAD term, evocative of cloud). Branding is a
founder decision; the vision-steward owns getting it confirmed or replaced.
Nothing else in the repo should hard-couple to the name.

## Brand hierarchy

1. **Overcastly AI** (https://overcastly.com) — the maker and company.
   Attribution belongs here ("Built by Overcastly AI").
2. **Loft** (working name) — the product: an open-source, MIT-licensed,
   cloud-native parametric 3D CAD platform. Its own identity, not
   white-labelled to Overcastly's visual language.
3. **Self-hoster branding** — a per-instance override layer (later phase).

## The thesis

**Build the best open-source parametric 3D CAD in the world — browser-based,
cloud-native, self-hostable — and compete with the industry leaders by doing
what a per-seat-licensed, file-format-locked, desktop-era product structurally
cannot.**

We don't win by out-checklisting SolidWorks' 30-year feature list. We win on
**structural advantages the incumbents can't match**:

1. **Free & unlimited.** Incumbent seats run $2,000–$4,500/yr, and the "free"
   tiers (hobbyist Fusion 360, Onshape free) hold your documents hostage —
   public-only files, export limits, features gated. Ours runs on your
   hardware; the marginal seat is $0.
2. **Your data, your files, your compute.** Open document format, direct DB
   access, STEP-first interop, no cloud lock-in. A regulated or IP-sensitive
   shop can run the whole stack air-gapped — the one thing no incumbent cloud
   CAD sells at any price.
3. **Open & extensible.** MIT license. Python is not a bolted-on macro
   language — the modeling API *is* Python, the same code path the UI uses.
   Code-level extensibility instead of a marketplace tax.
4. **AI-native & agent-native.** Built in the agent era: an MCP server lets a
   coding agent create sketches, run features, and export STEP directly.
   Parametric modeling is a language-shaped problem; no incumbent exposes
   their kernel to agents as a first-class surface. (This product is itself
   built by a team of AI agents — we dogfood the workflow.)

If a capability doesn't exploit one of those four advantages, it's table
stakes we ship to be credible — not where we differentiate.

## The operating question

Every roadmap decision, backlog item, and code review answers one question:

> **"Would a working engineer model a real part in this today?"**

Not "is it a promising demo" — a daily-driver bar. Where the honest answer is
"no," the scorecard row below says why, and that gap is the next thing we
build.

## Daily-driver scorecard

Rated against the incumbent daily drivers (SolidWorks / Fusion 360 / Onshape)
and the open-source incumbent (FreeCAD). Legend: ✅ better · ➖ parity ·
❌ behind · **PENDING** (evidence in flight — not yet a verdict, see
"Freshness discipline" below). Re-scored by the vision-steward each audit
cycle — honestly.

**Notes-cell format, mandatory from this pass on:** every cell opens with a
bolded marker, either `Re-derived <date> @ <short-sha>` (checked directly
against source/tests on that commit) or `PENDING — awaiting <X>` (do not
score from memory while X is in flight). Full flip-by-flip history for every
row lives in `docs/CHANGELOG.md`'s "2026-09-15 (VISION.md scorecard archived
by vision-steward — freshness pass)" section — this table carries the
CURRENT verdict and its evidence, not an archaeology of every prior flip.

| Dimension | Status | Notes |
|---|---|---|
| Sketching & constraints | ✅ | **Re-derived 2026-09-15 @ `21a039f`.** All twelve constraint kinds, splines (coincident/fixed/symmetric on fit points), dimension expressions (arithmetic, driving/driven), and over/conflict diagnosis — on both new-constraint authoring AND dimension-*value* edits — are shipped and verified directly against source (`services/geometry/src/geometry/sketch/planegcs_solver.py`: `_constraints_satisfied`/`settle()`). SNAP-5 (H/V inference on line-by-line draw) shipped, closing last cycle's DOF-parity residual. A P0 solver-perf regression a later audit found (a 48-line edit: 8.3 ms → 12,944 ms) is closed (`SETTLE-PERF-1`, verified live in source, cost cited at ~15 ms). Real residuals, narrower than incumbent parity, unchanged: spline tangency (G1, deferred pending a native planegcs primitive); no direct point-pair distance/H-V (routes through a linked line); expression grammar is arithmetic-only (no trig/units/named functions). Full flip history (SOLVE-1/SETTLE-2/SETTLE-3 and two same-day 2026-08-21 corrections): `docs/CHANGELOG.md`. |
| Part modeling (features, history) | ✅ | **Flipped ➖→✅ this pass. Re-derived 2026-09-15 @ `21a039f`.** The three defects that held this row at ➖ — NAME-2 (edge naming breaking on a SECOND edit to the same part), PICK-2 (the "Re-pick face" repair button was inert), EXPORT-3 (one failed downstream feature disabled export of the whole tree, including the good body already built) — are closed, verified directly in source, not inherited from BACKLOG's own "CLOSED" tags: `resolve_edge_durable()` (`services/geometry/src/geometry/kernel/edges.py`) gives edges the same durable two-tier re-match faces already had; PICK-2 guards (`apps/web/src/components/HoleEditor.tsx`, `SketchStrip.tsx`) refuse a pick with a stated reason instead of arming over nothing; `exportGate` (`CreateStrip.tsx`, `ExportToolGroup.tsx`) separates a partial-tree CAUSE from the healthy prefix. Sketch → extrude/revolve/sweep/loft → fillet/chamfer(click-specific-edge) → pattern → shell → draft → holes, multi-body booleans, datum planes, and timeline suppress/patch-mid-tree-feature all remain shipped. Residual, real but minor: no drag-to-reorder in the feature timeline; NAME-2b (P2, open) is an observability nicety layered on the NAME-2 fix (surfacing a re-anchor chip), not a correctness gap. Full flip history: `docs/CHANGELOG.md`. |
| Assemblies & mates | ➖ | **Flipped ❌→➖ this pass, correcting a 19-day-stale ❌ — this is the incident that prompted this audit.** The row moved to ❌ on 2026-08-22 solely on **MATE-1** (an occluded mate-target face, "blocks the entire Assemblies pillar"); MATE-1 closed **2026-08-27** (`a2a6f9f`, gated `1ae3270`) and the row was never re-scored — it was used as live evidence for a founder-facing "you cannot build a machine" claim earlier in this session, before this correction caught it. Verified independently against source this pass, not merely adopted from `docs/design/DIRECTION-ASSEMBLIES.md` (though it agrees): document model, 5-mate solver, flat BOM, interference detection, bidirectional assembly STEP, and undo/redo all check out. Held short of ✅, not ❌: no assembly has ever been solved or rendered past **2 instances** (`services/geometry/tests/test_assembly_export.py::_many_instance_request` goes to 20, but only to test STEP-export naming — no number exists anywhere in this repo for how long a 30-part assembly takes to solve/render); the BOM is explicitly non-recursive into sub-assemblies (`services/documents/src/documents/assemblies.py:532-533`, "NOT recursive into rigid sub-assemblies"); mate authoring has no assisted/auto-mate step. An ordinary few-part bolted assembly with interference checking and a parts list works today — that clears the daily-driver bar the ❌ denied. Re-derived 2026-09-15 @ `21a039f`. Full flip history: `docs/CHANGELOG.md`. |
| Interop (import + export) | ➖ | **Re-derived 2026-09-15 @ `21a039f` — no new evidence found, unchanged.** STEP import + export (bidirectional, multi-solid, multi-lump, named assembly product-structure) and 3MF/glTF/GLB export are shipped. IGES (either direction) and mesh-healing/repair for messy real-world CAD remain unbuilt; the feature-tree representation is inline-only (no blob-backed large-file path). Four formats against Fusion's eleven. Full history: `docs/CHANGELOG.md`. |
| Drawings & documentation | ➖ | **Re-derived 2026-09-15 @ `21a039f`.** Document model, exact HLR projection, model-true dimension measurement with a durable two-tier anchor (survives a FIRST *and* SECOND edit to the referenced edge), server-composed SVG/PDF/DXF (one placement source), section views, and associative re-layout on model change are shipped. **DXF-5** (every exported DXF declaring `$INSUNITS` = METRES instead of MM) — flagged last pass as the one open P0 on this row's export path — is CLOSED, verified in source (`services/geometry/src/geometry/drawings/compose.py`, `_new_dxf_document`/`$INSUNITS` guard). Real residuals, unchanged: part drawings only (no assembly drawings); no detail/broken/auxiliary views; no auto-dimensioning; no GD&T/tolerances/weld symbols; no drag-to-place. Full history: `docs/CHANGELOG.md`. |
| Sheet metal | ➖ | **Flipped ❌→➖ this pass — an independently-found SECOND instance of the exact Assemblies incident above.** The row moved to ❌ on 2026-08-22 on three P0s — **DXF-4** (flat-pattern export ships zero circles for through-holes — "a cut file that silently omits every through-feature"), **DXF-5** (shared with the Drawings row above), **EDGEFLANGE-1** (an edge flange can fold off a sheet's own thickness edge with no warning) — and was never re-scored. All three verified CLOSED directly in source: through-feature development is now load-bearing machinery, not an afterthought (`services/geometry/src/geometry/sheet_metal/{cutouts,unfold,flat_pattern}.py`, extensive `DXF-4` comments at every call site); `$INSUNITS` fixed (shared fix, Drawings row); a sheet-face guard refuses a thickness-edge flange (`services/geometry/src/geometry/sheet_metal/edge_flange.py`, "SHEET-FACE GUARD (EDGEFLANGE-1"). Base+edge flange, closed hem with corner relief, and multi-format flat-pattern export remain shipped and QA'd. Held at ➖, not ✅: the unfold is still an explicit depth-1 bend star — a flange-off-a-flange (a bend chain, what an enclosure/chassis needs) is a typed refusal, not silently wrong output, but it is still refused; no jog, miter flange, or gauge/material rule table (`docs/ROADMAP.md` Phase 4, "remaining v2 increments"). Re-derived 2026-09-15 @ `21a039f`. Full flip history: `docs/CHANGELOG.md`. |
| Workspace & document management | ➖ | **Re-derived 2026-09-15 @ `21a039f` — no new evidence found, unchanged.** Folders, search/sort/rename/duplicate, per-folder name uniqueness, and named (not UUID) export filenames are shipped. No thumbnails — the standing residual (`apps/web/src/routes/PartsPage.tsx` has none; needs a last-evaluated-mesh snapshot pipeline, per `docs/ROADMAP.md`). Full history: `docs/CHANGELOG.md`. |
| Performance on real parts | ➖ | **PENDING — a gauntlet is measuring a real imported STEP part and a 150–300-feature parametric part (kernel + browser) in this same session; treat the rest of this cell as the LAST full derivation (2026-08-21), not this pass's verdict.** `docs/PERF.md`: rebuild time grows N^1.85 across N=10–200 features ("fine at 25, a modeller waits at 50, painful at 100, unusable at 200"); a real 5-feature part measured end-to-end as "competitive with Fusion" (`docs/AUDIT-PRODUCT.md` R-13). Five perf defects (PERF-1..5: no rebuild cache, a validity-gate tax, STEP-import-of-own-export scaling faces^2.4, uncompressed mesh transport, per-face provenance going dark past ~110 features) were OPEN as of that date and have not been re-checked this pass. Re-score once the in-flight gauntlet reports. Full history: `docs/CHANGELOG.md`. |
| Collaboration & versioning | ❌ | **Re-derived 2026-09-15 @ `21a039f`.** Not started — document versioning, realtime presence, and Helm/HA all remain the unbuilt remainder of Phase 3 (`docs/ROADMAP.md`). Unchanged. |
| Extensibility (scripting API) | ❌ | **PENDING — SCRIPT-1 (the public Python scripting API) is in flight this session** (`docs/BACKLOG.md`, dispatched groom pass 24; `docs/ROADMAP.md` Phase 5). Python-first design holds kernel-side (the modeling API is Python, the same code path the UI drives through `services/geometry`), but no external-facing scripting surface exists yet. Re-score once SCRIPT-1 lands. Re-derived 2026-09-15 @ `21a039f`. |
| Agent access (MCP) | ❌ | **PENDING — the MCP server sits on top of SCRIPT-1 and has not started.** Designed-for (`docs/ROADMAP.md` Phase 5), not shipped. Re-score once SCRIPT-1 lands and MCP work begins. Re-derived 2026-09-15 @ `21a039f`. |
| Free & unlimited (self-hosted, air-gapped) | **PENDING** | **Retitled + re-scored PENDING this pass (vision-steward), replacing "Price / freedom" / ✅ ("MIT, self-hosted, unlimited — true from day one").** That ✅ was scored off the thesis sentence (advantage #1), not off empirical verification of its harder half — that the app can genuinely run air-gapped with no phone-home to the public internet. MIT license + no per-seat metering is true by construction (`LICENSE`; no telemetry/license-check code found in a light grep). Whether the running app reaches the public internet at all, and whether self-hosting actually works end to end, is being verified empirically **this session** into `docs/AUDIT-ENGINEERING.md` by a sibling pass. Held PENDING, not ✅, until that lands: an aspirational ✅ on our OWN hardest-differentiated claim is exactly the failure this freshness pass exists to catch. Re-derived 2026-09-15 @ `21a039f`. |
| Your data, your files, your compute | **PENDING** | **New row, added this pass (vision-steward) — advantage #2 (`docs/VISION.md` thesis) had no scorecard row at all**, the same "an unexamined dimension reads as fine" gap the Workspace row was added to fix on 2026-07-30. Claims to verify: open document format / direct DB access (a real Postgres schema, not an opaque blob, by architecture — `services/documents`); STEP-first interop (true, see the Interop row); no cloud lock-in (self-hostable via Docker Compose/Helm — `deploy/` exists, not exercised end-to-end this pass). Scored PENDING: the same `docs/AUDIT-ENGINEERING.md` pass verifying the row above covers whether a user can actually get their data out and self-host; score this row off THAT evidence, not the thesis sentence. Re-derived 2026-09-15 @ `21a039f`. |

**Counts this pass:** 2 ✅ (Sketching & constraints, Part modeling) · 6 ➖
(Assemblies & mates, Interop, Drawings, Sheet metal, Workspace, Performance)
· 3 ❌ (Collaboration, Extensibility, Agent access) · 2 **PENDING** (Free &
unlimited, Your data/files/compute). Of the 6 ➖ rows, one (Performance) and
of the 3 ❌ rows, two (Extensibility, Agent access) carry an explicit
**PENDING** marker inside their cell because evidence is in flight this same
session — their letter grade is last-known, not re-verified here.

**What moved this pass and why (2026-09-15, vision-steward, against
`21a039f`):** **Assemblies & mates ❌→➖** — the incident this pass exists to
fix: MATE-1 closed 08-27, the row sat at ❌ until now, and was cited as
evidence for a founder-facing claim before the correction. **Sheet metal
❌→➖** — an independently-found second instance of the identical incident
class: its own three blocking P0s (DXF-4/DXF-5/EDGEFLANGE-1) closed shortly
after the same 08-22 flip and were never re-scored either. **Part modeling
➖→✅** — its three blockers (NAME-2/PICK-2/EXPORT-3) are closed. **Two new
rows** for advantages #1 and #2, both **PENDING** on `docs/AUDIT-ENGINEERING.md`
rather than scored from the thesis. No other row changed grade; Sketching,
Interop, Drawings, Workspace, Collaboration are re-derived and hold.
Performance, Extensibility, Agent access are explicitly flagged PENDING
in-place rather than re-scored from memory.

**The lesson, stated once rather than re-litigated per row:** every stale
row this pass shared one shape — a ❌ (or ➖) flip justified by a NAMED,
CITED defect ("this blocks the entire pillar"), that defect closing, and
nobody re-running the citation. A scorecard that names its own falsification
condition and then never checks it is worse than one with no reasoning at
all, because the reasoning makes it *look* current. See "Freshness
discipline" below for the mechanism this pass adds to catch the next one
mechanically rather than by luck.

### Freshness discipline

**The property that must hold:** a reader can tell a fresh row from a stale
one WITHOUT re-deriving it. Two parts, one already in force above, one
proposed for automation.

1. **Every cell's marker is load-bearing, not decorative.** `Re-derived
   <date> @ <sha>` names the exact commit the row was checked against;
   `PENDING — awaiting <X>` names exactly what would resolve it. A cell with
   neither is itself a defect from this pass forward — flag it in the next
   audit rather than reading it as fresh.
2. **A row is STALE the moment a commit lands, after its cited SHA, that
   touches the paths its verdict depends on** — regardless of whether that
   commit *changes* the verdict. This is the exact failure this pass fixes:
   MATE-1's closing commit (`a2a6f9f`) landed after the Assemblies row's
   citation and nobody asked "did anything touch this row's territory
   since?" A mechanical check can ask that question even though it cannot
   answer whether the verdict itself is still right — and that is enough to
   turn "stale for 19 days, unnoticed" into "flagged the same day."

**Proposed mechanical check — not yet built; specification for whoever
implements it (`scripts/check-scorecard-freshness.py` is the natural name,
stdlib + `git`, no daemon, same shape as `check-build-context.py`):**

For each scorecard row, parse its Dimension name and its cited
`Re-derived … @ <sha>` (rows marked `PENDING` are exempt — there is no
citation to go stale). Maintain a small, hand-maintained map of Dimension →
territory paths (the same paths a builder's brief would name):

| Dimension | Territory (globs) |
|---|---|
| Sketching & constraints | `services/geometry/src/geometry/sketch/**`, `apps/web/src/sketch/**` |
| Part modeling | `services/geometry/src/geometry/{features,kernel}/**`, `apps/web/src/routes/PartPage.tsx`, `apps/web/src/components/{HoleEditor,SketchStrip,CreateStrip,ExportToolGroup}.tsx` |
| Assemblies & mates | `services/documents/src/documents/assemblies.py`, `services/geometry/src/geometry/assembly/**`, `apps/web/src/assembly/**`, `apps/web/src/viewport/AssemblyScene.tsx` |
| Interop | `services/geometry/src/geometry/kernel/export.py`, `**/import_step.py` |
| Drawings & documentation | `services/geometry/src/geometry/drawings/**`, `apps/web/src/drawing*/**` |
| Sheet metal | `services/geometry/src/geometry/sheet_metal/**` |
| Workspace & document management | `apps/web/src/routes/PartsPage.tsx`, `apps/web/src/api/parts.ts` |
| Performance on real parts | `docs/PERF.md`, `services/geometry/tests/test_benchmarks.py` |
| Free & unlimited / Your data, your files | `docs/AUDIT-ENGINEERING.md`, `deploy/**`, `LICENSE` |

(Collaboration/Extensibility/Agent access have no territory yet — nothing to
watch until the surface exists; add rows here as SCRIPT-1/MCP land.)

For each mapped row: `git log -1 --format=%H -- <territory paths>` gives the
newest commit touching it. If that commit is not an ancestor of the row's
cited SHA (`git merge-base --is-ancestor <newest> <cited-sha>`; nonzero exit
= not an ancestor = the newest commit POSTDATES the citation), print the row
as STALE, naming the offending commit. This cannot tell you whether the
verdict is still correct — only a human re-derivation can — but it turns
"did anything change here since I last looked" from a manual sweep across
every row into one command, and it is precisely the question that went
unasked for 19 days on Assemblies and longer on Sheet metal.

**Where to wire it:** `doc-syncer`'s pass (cheap-model, runs every
iteration, already reconciles docs against `git log`) is the natural home —
have it print a one-line STALE/FRESH table as part of its normal output, not
block anything. Also run it as the FIRST step of every vision-steward audit
cycle, replacing "which rows might need a look" guesswork with a computed
list to start from. Do not make it a CI gate: staleness is a prompt to
re-derive, not proof the verdict is wrong, and a hard gate on doc-vs-code
timing would block unrelated commits for no reason.

## Design mandate (founder, 2026-07-09)

**Frontend design is a stated founder priority, on par with geometric
correctness.** The product must look and feel premium, distinctive, and
intentional — a tool engineers are proud to live in all day — never
templated. Operationalized as the standing "Design mandate" section in
`CLAUDE.md` (mandatory `frontend-design` skill for all UI work, token-driven
design system, the viewport as hero, screenshots to the founder). Incumbent
CAD UIs are dated and cluttered; design is a real wedge, alongside the four
structural advantages above.

## What we are NOT building (for now)

- CAM, simulation/FEA, rendering — out of scope until the modeling core is a
  daily driver. Extensibility is the answer for these, not core features.
- A native desktop app. Browser-first; the viewport must earn it.
- Cloud SaaS billing. Self-hosted first; hosted offering is a company
  decision later, not a repo concern.
