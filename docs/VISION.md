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

**Notes-cell format, mandatory:** every cell opens with a bolded marker,
either `Re-derived <date> @ <short-sha> · <method>` (checked on that commit)
or `PENDING — awaiting <X>, opened <date>` (do not score from memory while X
is in flight). Full flip-by-flip history lives in `docs/CHANGELOG.md` — this
table carries the CURRENT verdict and its evidence, not an archaeology of
every prior flip.

**The `· <method>` field is NEW as of 2026-09-16 and it is the correction this
pass exists to make.** A date and a sha say WHEN a row was checked; they say
nothing about HOW DEEPLY, and depth is what failed here. Three methods, in
descending strength, each carrying its own date because they decay at
different rates:

- **`· live app <date>`** — somebody drove the running product through the
  flow this row is about and measured the result. The only method that can
  support a founder-facing claim.
- **`· source <date>`** — read against the shipped code. Catches "is it
  built"; cannot catch "does it work for the user", and **cannot catch a
  misreading of what the code guarantees** — which is exactly how this
  table's `Part modeling` ✅ was manufactured one day before this pass.
- **`· churn-only`** — the only thing checked was whether the commits that
  landed in this row's territory COULD have changed the verdict (e.g. a
  packaging move). A legitimate, cheap answer to the decay question and **no
  answer at all to the verdict question.** A row whose deepest check is
  `churn-only` is CARRIED OVER, not re-derived; say so in the cell and never
  quote it as live evidence.

**A `PENDING` must name a date and the thing that would resolve it, and a
`PENDING` older than one audit cycle is a DEFECT, not a state.** Board item
#64 named the old unbounded form correctly: `PENDING` is exempt from the
freshness gate, so an un-bounded one is a self-granted permanent exemption —
a row that can never be reported stale because it has declared itself
un-scorable. This pass found **five** PENDING rows, **three of whose awaited
evidence had already landed** (the gauntlet, SCRIPT-1, the air-gap
verification) and which were still sitting exempt. All five are resolved
below; there are now zero. If you mark a row PENDING, you owe it a verdict
the next cycle or an explanation of why the evidence did not arrive.

| Dimension | Status | Notes |
|---|---|---|
| Sketching & constraints | ➖ | **Flipped ✅→➖ this pass — MY call, not the audit's recommendation; if you challenge one verdict here, challenge this one. Re-derived 2026-09-16 @ `93733b2` · live app 2026-09-16.** The ✅ was scored off the SOLVER (`services/geometry/src/geometry/sketch/planegcs_solver.py`, `_constraints_satisfied`/`settle()`) and never off the sketcher as a place to work. The first live session to grade this dimension (`docs/AUDIT-PRODUCT.md` 2026-09-16) rates draw-and-dimension-at-the-cursor **4.5/5** — drag-draw, W/H typed at the cursor, `Enter`, 120×80 in one gesture; `c` applied coincident and DOF went 2→0 in 1.7 s — and rates sketch VIEW CONTROL **2/5**: there is no Fit, Home or zoom-to-selection in sketch mode (`view-fit`/`view-home` testids absent), an ordinary coincident constraint translated the profile until one edge remained on screen (recovered by six manual scroll notches), and after a dimension edit the 80 mm glyph sat at **x = 1856 on a 1600 px frame**. Editing an existing sketch rates 2.5/5 — the solid body is drawn OPAQUE over the profile you are editing. Constraint capability is unchanged and still at-or-above incumbent parity: twelve kinds, splines (coincident/fixed/symmetric on fit points), driving/driven dimension expressions, over/conflict diagnosis on both authoring and value edits, H/V inference on line-by-line draw (SNAP-5). The P0 solver-perf regression a prior audit found (8.3 ms → 12,944 ms) stays closed (SETTLE-PERF-1, ~15 ms). **➖ is the net, and the reasoning is the point: the dimension is the sketching ENVIRONMENT, not only the solver.** An engineer gets a better constraint engine than Fusion's and loses their view twice a sitting with no key to get it back. Residuals unchanged: spline tangency (G1, deferred pending a native planegcs primitive); no direct point-pair distance/H-V (routes through a linked line); expression grammar arithmetic-only (no trig/units/named functions). Flip back to ✅ when Fit/Home lands in the sketcher and the body ghosts during a sketch edit. Full flip history: `docs/CHANGELOG.md`. |
| Part modeling (features, history) | ➖ | **Flipped ✅→➖ twenty-four hours after the ✅ — and the ✅ was WRONG WHEN WRITTEN, not decayed. That distinction is the most important thing on this table; see "Freshness discipline". Re-derived 2026-09-16 @ `93733b2` · live app 2026-09-16 + source probe at `3ff8db9`.** The ✅ cited `resolve_edge_durable()` as giving edges "the same durable two-tier re-match faces already had". **Faces have FOUR tiers and edges have two, and `services/geometry/src/geometry/kernel/edges.py`'s own module docstring says so** ("A face has had four tiers since M17/GEOM-3"). The code never claimed parity; the scorecard cell read the fix's NAME instead of its invariant. And edge tier 2 is invariant under the wrong thing. Measured this pass directly against the shipped predicate (`durable_edge_match`, stdlib probe, no kernel): the stored vertical corner edge `(120,0,0)→(120,0,40)` re-matches after an extrude-depth change 40→60 — it grows ALONG ITSELF — **True**; after a width change 120→150, which TRANSLATES it to a parallel line — **False**, and still False at **0.0005 mm** of perpendicular offset. `collinear_overlapping_match` requires the edge to lie on its original supporting line, so **a dimension change cannot fire tier 2 by construction, not by tolerance** — and a dimension change is always a translation. Live consequence on a real six-feature part at `93733b2`: width 120→150 gave `Fillet1 ERR SUBSHAPE_UNRESOLVED` and `Shell1`/`Hole1`/`Pattern1 SKIP`, collapsing the part to a bare block — **480,000 mm³, 6 faces, four of six features destroyed by one ordinary edit** — while every FACE reference in the same tree re-resolved through 120→150→130. **The residual this row filed ("no drag-to-reorder") is not the residual. The edit loop is.** **The three blockers that had held this row at ➖ really are closed, and this correction does not reopen them** — NAME-2 (edge naming breaking on a second edit), PICK-2 (`apps/web/src/components/HoleEditor.tsx`, `SketchStrip.tsx` now refuse a pick with a stated reason), EXPORT-3 (`exportGate` in `CreateStrip.tsx`/`ExportToolGroup.tsx` separates a partial-tree cause from the healthy prefix); NAME-2b (P2, open) remains an observability nicety. What was false was the PARITY claim layered on top of them. Authoring is genuinely strong and unchanged — sketch → extrude/revolve/sweep/loft → fillet/chamfer → pattern → shell → draft → holes, multi-body booleans, datum planes, timeline suppress/patch-mid-tree; fillet BY RULE beats anything Fusion offers on a prismatic part; the partial-body failure surface is best-in-class. Not ❌, because the parametric loop itself works: repairing `Fillet1` to BY RULE rebuilt all six features and a SECOND edit 150→130 then rebuilt cleanly. The defect is localised to picked-edge references — which is what anyone uses on anything non-prismatic. Flip to ✅ when a golden widens a filleted+shelled+patterned box by 30 mm and every feature rebuilds. Full flip history: `docs/CHANGELOG.md`. |
| Selection & picking | ➖ | **NEW ROW, added this pass (vision-steward) — the THIRD consecutive product audit whose findings shared a cause no row could hold, and the two earlier requests were not acted on. Re-derived 2026-09-16 @ `dbddb17` · live app 2026-09-16 + gauntlet 2026-09-15.** **Opens at ➖, not ❌, and the direction is UP:** hover-highlight and real-geometry face picking both WORK now — hovering tints the real face (**6,889 of 13,500** sampled pixels change) and a real `page.mouse.click` at a point where `elementFromPoint` returns only `CANVAS` picks the face, because the raycast lives in GL and wins. Any future audit that judges picking by `elementFromPoint` alone will repeat that error. Against that, the DRAWN markers lie about what is under them, systematically — measured at each proxy's own centre: on Hole, an inner wall's marker sits **9 px** from its outer twin's and resolves to it; on Shell, `shell-face-1` is the BOTTOM face drawn at a screen point inside the visible FRONT wall, so "click the middle of the front wall" opens the bottom; on Fillet, the radius gauge sleeve lands exactly on `edge-pick-4`, so a picked edge cannot be un-picked; Measure draws **110 markers at once, 48 of them (44 %) unreachable at their own centre**. Three of twelve edges are correctly buried behind the solid, but with no cue and no "select other" the audit shipped a three-cornered fillet on a four-cornered box without noticing (volume confirms: 382,351.86 mm³ = 384,000 − 3 × 549.4). On a REAL part the density was the wall: **452** overlay nodes, 17.5 s to settle, **55–73 s to select one face** (`docs/GEOMETRY-QA.md` browser leg) — **and that half was substantially fixed by `9083f0a` WHILE THIS ROW WAS BEING WRITTEN**, which is the freshness gate doing its job inside one hour rather than 19 days. drei's `Html` was calling `ReactDOM.createRoot` PER INSTANCE, so 452 marks were 452 React roots — ~13 s of main-thread script, a hang rather than a slowdown; they now share one host, one root and one projection pass, measured at **3.5x** per mark and, more importantly, **flat instead of super-linear** (N=113/452/904 all ~0.30 ms/mark against 1.08–1.32 before). **The 55–73 s figure is NOT re-measured and is now an UPPER BOUND predating that commit** — treat it as such until somebody drives a 1,000-face part again. The verdict does not move, because the settle cost was never the whole of this row: the collisions, the 44 %-unreachable census and Measure's mislabelling are all untouched by a perf fix. Measure also hands back a number an engineer will act on and get wrong: a 25 mm hole pitch reads as a bare `DISTANCE 17 mm` — the minimum circle-to-circle distance, unlabelled, with no centre-to-centre option, on the most common measurement taken on a plate. Flip to ✅ when markers draw on hover instead of all at once and a pick on a 1,000-face part is sub-second. |
| Assemblies & mates | ➖ | **Grade CARRIED OVER — not re-derived against the running app this pass. Re-derived 2026-09-16 @ `dbddb17` · churn-only; deepest check: source 2026-09-15, live app 2026-08-27.** The gate reported this row STALE on `14f6e14`. That commit is the wire-types packaging split (33 deps → 15, an import-path move across 264 files) and cannot change an assemblies verdict — which answers the DECAY question and not the VERDICT question. The ➖ still rests on the 2026-09-15 source derivation (which agrees with `docs/design/DIRECTION-ASSEMBLIES.md` rather than merely adopting it): document model, 5-mate solver, flat BOM, interference detection, bidirectional assembly STEP, undo/redo. Held short of ✅ for the same three reasons: no assembly has been solved or rendered past **2 instances** (`services/geometry/tests/test_assembly_export.py::_many_instance_request` goes to 20, but only to test STEP-export naming), and no number exists anywhere in this repo for how long a 30-part assembly takes to solve/render; the BOM is explicitly non-recursive into sub-assemblies (`services/documents/src/documents/assemblies.py:532-533`); mate authoring has no assisted/auto-mate step. **Nobody has driven an assembly in the running app since 2026-08-27 — do not cite this row as live evidence for a founder-facing claim.** That is the same mistake this row's own 19-day ❌ produced. Full flip history: `docs/CHANGELOG.md`. |
| Interop (import + export) | ➖ | **Held ➖ on the strongest empirical support this row has ever had — new evidence, unchanged grade. Re-derived 2026-09-16 @ `dbddb17` · gauntlet 2026-09-15 + live app 2026-09-16.** `just gauntlet` (`docs/GEOMETRY-QA.md`) measured **five real STEP files authored in somebody else's CAD** — Open CASCADE/Datakit, Siemens NX 7.5, Autodesk Inventor 2018 — from a 160-face conformance assembly to a 10,665-face / 211-solid suspension. All five import inside the shipped bounded path (20 s CPU / 60 s wall), round-trip volume to ≤1.0e-3 relative, and **topology exact on four of the five**. The audit's own live round-trip reproduced 73,878.13 mm³ / 51,074.07 mm² / 27 faces / 72 edges exactly from a 95,622-byte AP214. This is the axis a generated fixture cannot test, and it held. Two NEW residuals, both measured: the 211-solid part's round-trip topology **DIFFERS**; and the **16 MiB** `MAX_INLINE_STEP_CHARS` cap is real and close — the 15 MB fixture sits at **89 %** of it, so a part 12 % larger is a 422 at the boundary rather than a slow import (and `py_kit/schemas/step_import.py`'s docstring says 32 MiB, which is stale). Unchanged and still shipped: STEP import + export (bidirectional, multi-solid, multi-lump, named assembly product-structure) plus 3MF/glTF/GLB export. Unchanged residuals: IGES in neither direction, no mesh healing/repair for messy real-world CAD, four formats against Fusion's eleven, an inline-only feature-tree representation with no blob-backed large-file path, and a STEP header carrying a fixed `2000-01-01T00:00:00` epoch with a literal `Author` — which PDM systems key on. Full history: `docs/CHANGELOG.md`. |
| Drawings & documentation | ➖ | **Grade CARRIED OVER — not re-derived against the running app this pass. Re-derived 2026-09-16 @ `dbddb17` · churn-only; deepest check: source 2026-09-15.** STALE was reported on `14f6e14`, the wire-types packaging split — an import-path move that cannot change a drawings verdict. The ➖ rests on the 2026-09-15 source derivation: document model, exact HLR projection, model-true dimension measurement with a durable two-tier anchor, server-composed SVG/PDF/DXF from one placement source, section views, associative re-layout, and DXF-5 closed — every exported DXF had declared `$INSUNITS` as METRES instead of MM (`services/geometry/src/geometry/drawings/compose.py`, `_new_dxf_document`). Residuals unchanged: part drawings only (no assembly drawings), no detail/broken/auxiliary views, no auto-dimensioning, no GD&T/tolerances/weld symbols, no drag-to-place. **Note the drawings dimension anchor is the FACE-style durable match, not the edge one the Part modeling row just failed on — that is an asymmetry worth re-checking live rather than assuming.** Full history: `docs/CHANGELOG.md`. |
| Sheet metal | ➖ | **Grade CARRIED OVER — not re-derived against the running app this pass. Re-derived 2026-09-16 @ `dbddb17` · churn-only; deepest check: source 2026-09-15.** STALE was reported on `14f6e14`, the wire-types packaging split — an import-path move that cannot change a sheet-metal verdict. The ➖ rests on the 2026-09-15 source derivation that closed its three blocking P0s: flat-pattern export no longer ships zero circles for through-holes (a cut file that silently omitted every through-feature) — through-feature development is now load-bearing machinery (`sheet_metal/{cutouts,unfold,flat_pattern}.py`, DXF-4), `$INSUNITS` fixed (DXF-5, shared with Drawings), and a sheet-face guard refuses a thickness-edge flange (`services/geometry/src/geometry/sheet_metal/edge_flange.py`, EDGEFLANGE-1). Base + edge flange, closed hem with corner relief, and multi-format flat-pattern export are shipped and QA'd. Held at ➖: the unfold is still an explicit depth-1 bend star — a flange-off-a-flange, which is what any enclosure or chassis needs, is a TYPED REFUSAL rather than wrong output, but it is still refused; no jog, miter flange, or gauge/material rule table (`docs/ROADMAP.md` Phase 4). Full flip history: `docs/CHANGELOG.md`. |
| Workspace & document management | ➖ | **Grade CARRIED OVER — not re-derived against the running app this pass. Re-derived 2026-09-16 @ `dbddb17` · churn-only; deepest check: source 2026-09-15.** STALE was reported on `6ffdcda`, which repaired web-side drift guards that had died at COLLECTION when the wire schemas moved — test plumbing following the same packaging split, not a workspace change. Folders, search/sort/rename/duplicate, per-folder name uniqueness, and named (not UUID) export filenames are shipped. Standing residual unchanged: no thumbnails (`apps/web/src/routes/PartsPage.tsx`; needs a last-evaluated-mesh snapshot pipeline). Full history: `docs/CHANGELOG.md`. |
| Performance on real parts | ❌ | **Flipped ➖→❌ this pass, and the exemption it carried is DISCHARGED — the gauntlet reported. Re-derived 2026-09-16 @ `ecb9df8` · gauntlet 2026-09-15 (`docs/GEOMETRY-QA.md`) + live app 2026-09-16.** (Citation advanced past `373304c` in the same pass: widening this row's territory to cover `scripts/gauntlet.py` — see below — immediately flagged it, and it is manifest validation that touches no measured number. Recorded rather than silently re-cited, because a STALE line nobody explains is how a gate gets muted.) ➖ claimed parity. The numbers do not support parity. **Kernel leg, load-immune:** a 250-feature part cold-rebuilds in **51.7 s**, and **an edit costs a full rebuild** — `edit/cold` = 0.89–1.08 across four measurements — with editing feature **#3** costing the same as editing **#249** (48.4 s vs 46.0 s), i.e. there is no rebuild cache and depth buys nothing. Scaling re-measured at **~N^2.15** (consistent with `docs/PERF.md`'s earlier N^1.85 given ±15 % load noise and a longer arm; PERF.md's own words: "fine at 25, a modeller waits at 50, painful at 100, unusable at 200"). The ratio is the claim and it is clock-independent: both halves of each pair are taken in one process within one minute, and re-running N=250 in a quiet window (load 1.17) made the edit figures *higher*, not lower — so contention was not inflating them. **Browser leg, the same real part** (gearbox-11752, 1,018 faces): open part → properties **12.6–14.1 s**; arm a face pick → prompt **30–41 s**; click a face → prompt cleared **25–32 s**, so **selecting one face costs 55–73 s**, with **452** DOM overlay nodes taking 17.5 s to settle and a **10.41 MB** uncompressed mesh over HTTP. Fusion, Onshape and SolidWorks do all of this interactively. **Partly superseded already: `9083f0a` (2026-09-16) removed ~13 s of main-thread script from the mark mount and made it flat in N (see the Selection & picking row), so the pick figures above are an UPPER BOUND, un-re-measured.** The KERNEL numbers are untouched by it and they are the ones carrying this ❌. **What is genuinely fine, so the row is not read as blanket-slow:** import of real foreign parts (see Interop), a 6-feature part end-to-end in **2.27 s**, N=100 cold in 7.3 s, and `repeat` at 66–235 ms. The wall is the EDIT at depth and the SELECTION on a dense body — the same two walls the Part modeling and Selection rows name, which is why this is one problem and not three. Frame rate is deliberately NOT scored: this container has no GPU and the measured 3,588 ms/frame orbit grades SwiftShader, not the hardware path (`docs/PERF.md` set that precedent — quote it as "the orbit did not complete under software GL", never as an fps figure). PERF-1..5 remain open and are exactly the mechanisms above: no rebuild cache, a validity-gate tax, STEP-import-of-own-export scaling faces^2.4, uncompressed mesh transport, and per-face provenance going dark past ~110 features. Flip back to ➖ when `edit/cold` is well under 0.2 at N=250 and a face pick on a 1,000-face part is sub-second. Full history: `docs/CHANGELOG.md`. |
| Collaboration & versioning | ❌ | **Held ❌, and now CONFIRMED in the running app rather than inferred from an empty directory. Re-derived 2026-09-16 @ `dbddb17` · live app 2026-09-16.** Document versioning, realtime presence and Helm/HA remain the unbuilt remainder of Phase 3 (`docs/ROADMAP.md`). The live cost is sharper than "not started" implies: after a page reload the Undo control reports ENABLED (`aria-disabled: null`, `disabled: false`) and does nothing, and there is no version history behind it — **a reload is a hard horizon on recovery.** Onshape's persistent version graph is a real differentiator against us here. **This row is UNMAPPED in the territory table below: nothing watches it, so it can never be reported stale.** That exemption is deliberate (no surface exists) and is itself the thing to re-check — add a territory the day versioning ships, or this row inherits the "forever fresh because watched by nothing" failure. |
| Extensibility (scripting API) | ➖ | **Flipped ❌→➖ this pass and its exemption is DISCHARGED — SCRIPT-1 SHIPPED. Re-derived 2026-09-16 @ `dbddb17` · source 2026-09-16.** (It had been marked `PENDING — awaiting SCRIPT-1`; SCRIPT-1 landed and the row sat exempt anyway.) `packages/loft-script` is real: a `loft` package with session/transport/part/sketch modules, typed errors, part and feature CRUD, sketch authoring, and evaluation with `raise_for_feature`/`raise_for_features`, carrying a `test_contract_parity` suite; the groomer records it as "two-path-proven identical to a browser-driven build" (`4e69434`). The thesis claim holds — the modelling API IS Python, the same code path the UI drives. **➖ and deliberately not ✅:** every incumbent daily driver already ships a scripting API (Fusion Python, SolidWorks VBA/C#, Onshape FeatureScript + REST) and FreeCAD is Python-native, so shipping one reaches parity rather than passing anyone. ✅ needs the half no incumbent has, which is the row directly below. Residuals: no published API reference or worked examples verified this pass, and no user outside this repo has driven it. Full history: `docs/CHANGELOG.md`. |
| Agent access (MCP) | ❌ | **Held ❌ — but its exemption is DISCHARGED and must not be silently re-asserted: the thing it was waiting on (SCRIPT-1) LANDED, and MCP still has not started. Re-derived 2026-09-16 @ `dbddb17` · source 2026-09-16.** No MCP server exists in the tree. Designed-for in `docs/ROADMAP.md` Phase 5. **This row now carries the whole of structural advantage #4, and it is the only ✅ on this table that no incumbent can answer at any price** — the substrate it sits on (`packages/loft-script`) now exists, so this is the highest-leverage ❌ on the board and the one place where breadth-for-breadth's-sake should lose to it. UNMAPPED in the territory table (no surface yet); add one the day the server lands. |
| Free & unlimited (self-hosted, air-gapped) | ✅ | **Flipped ⏳→✅ this pass: the empirical verification this row was holding out for LANDED, found the claim FALSE, and it was fixed with a gate the same day. Re-derived 2026-09-16 @ `dbddb17` · source 2026-09-16 (`725bc4b`, `scripts/check-air-gap.py`).** The PENDING was right to refuse the old ✅. Measured: every service booted with FastAPI's default `/docs` and `/redoc`, which source `cdn.jsdelivr.net`, `fastapi.tiangolo.com` and `fonts.googleapis.com` — on `:8000`, the one port a self-hoster publishes. A blank page on day one for exactly the air-gapped customer advantage #1 was written to win, and **no grep of our own tree could have found it**, because those URLs live inside the `fastapi` package. Fixed (`docs_url=None`/`redoc_url=None`; `/openapi.json` untouched and verified 200) and now GATED: `check-air-gap.py` grades six surfaces — backend string literals via AST, the `FastAPI(...)` construction, web source + markup, fonts, compose, Dockerfile runtime directives — each declaring a count floor that REFUSES below it, wired into `just lint` and CI. MIT plus no per-seat metering is true by construction (`LICENSE`; no telemetry or licence-check code). **✅ because no incumbent cloud CAD sells air-gapped operation at any price**, and because this is now the only claim on this table with a mechanical gate keeping it true rather than a paragraph asserting it. Residual: restoring an interactive API explorer needs ~3 MB of vendored swagger-ui — filed, not done. |
| Your data, your files, your compute | ✅ | **Flipped ⏳→✅ this pass on the same landed evidence. Re-derived 2026-09-16 @ `dbddb17` · source 2026-09-16 + gauntlet 2026-09-15.** Four claims, each now with something behind it rather than the thesis sentence the PENDING was created to refuse: documents live in a real Postgres schema a self-hoster can read directly, not an opaque blob (`services/documents`); **a backup/restore drill runs in CI on every commit** (`scripts/backup-restore-drill.sh`, `deploy-path` workflow) — getting your data OUT is a tested property, not a promise; STEP-first interop is proven against five real files authored in other people's CAD (Interop row); self-hosting boots from compose in the same workflow, air-gapped per the row above. **✅ because the incumbents cannot offer this at any price** — Onshape and Fusion hold your documents in their cloud and there is no `pg_dump`. **Method caveat, stated so it can be challenged rather than inherited: I verified the drill script EXISTS and is wired into the workflow; this session cannot read CI, so I have not seen it pass.** Residual, and the next thing to attack on this row: the feature tree has no documented PORTABLE file format — it is portable by virtue of the DB schema, which is a weaker claim than a specified open document format. |

**Counts (2026-09-16, 14 rows):** 2 ✅ (Free & unlimited; Your data, your
files, your compute) · 9 ➖ (Sketching, Part modeling, Selection & picking,
Assemblies, Interop, Drawings, Sheet metal, Workspace, Extensibility — of
which **four are CARRIED OVER**, `churn-only`: Assemblies, Drawings, Sheet
metal, Workspace) · 3 ❌ (Performance, Collaboration, Agent access) ·
**0 PENDING**, down from five. (Counts derived from the table, not tallied by
hand — my hand tally was wrong on the first attempt, which is the small
version of the same lesson this whole pass is about.)

**Read the shape before the rows, because the shape is the message: every ✅
on this table is a STRUCTURAL ADVANTAGE, and no capability row is above
parity.** That is not pessimism, it is the thesis working as intended — we
said we do not win by out-checklisting a 30-year feature list, and the table
now says plainly that we do not. It also says where the leverage is: `Agent
access (MCP)` is the only remaining ❌ that no incumbent can answer at any
price, and its substrate shipped this week.

**What moved, 2026-09-16 (vision-steward), and in which direction —
deliberately both ways.**

*Down, on running-app evidence:*
- **Part modeling ✅→➖.** The ✅ was twenty-four hours old and **wrong when
  written**. See the row; see the freshness section for why that matters more
  than the row.
- **Performance on real parts ➖→❌.** PENDING resolved: the gauntlet
  reported, and an edit at N=250 costs a full rebuild (`edit/cold` ≈ 1.0,
  load-invariant) while selecting one face on a real 1,018-face part costs
  55–73 s. ➖ meant parity; there is no reading of those numbers that is
  parity.
- **Sketching & constraints ✅→➖.** My call, not the audit's — the ✅ graded
  the solver and the dimension is the sketcher. No Fit/Home; an ordinary
  coincident constraint pushed the profile off-frame twice in one sitting.

*Up, on evidence that landed while the rows sat exempt:*
- **Free & unlimited PENDING→✅** and **Your data, your files,
  your compute PENDING→✅.** The air-gap claim was verified, found FALSE,
  fixed, and is now gated by `check-air-gap.py` in `just lint` and CI; the
  backup/restore drill runs in CI. These are the two rows that carry
  advantages #1 and #2, and they are the first ✅s on this table backed by a
  mechanical gate rather than a paragraph.
- **Extensibility (scripting API) ❌→➖.** PENDING resolved: SCRIPT-1 shipped
  (`packages/loft-script`). Parity, not better — every incumbent has one.

*New:*
- **Selection & picking ➖** — a row at last, after three consecutive audits
  whose findings shared a cause the table could not hold. It opens at ➖ and
  the direction is UP: face picking on real geometry works now.

*Held, with the method downgraded so the honesty is visible:* Assemblies,
Drawings, Sheet metal and Workspace are **CARRIED OVER**. The freshness gate
flagged all four STALE; the commits responsible are a packaging split and its
test-plumbing follow-up, which cannot change those verdicts. That answers the
decay question and not the verdict question, and the cells now say so.
Collaboration & versioning holds ❌, upgraded from inferred to live-confirmed.

**The lesson, and it is a DIFFERENT lesson from last pass's.** Last pass every
stale row shared one shape: a cited defect that closed while nobody re-ran the
citation — **decay**. The mechanical gate built for that works, and it fired
correctly this pass. This pass's headline row failed a way the gate cannot
see: the `Part modeling` ✅ was **false on the day it was written**. Nothing
had to change for it to be wrong. It was derived by reading a fix's NAME
(`resolve_edge_durable`, "two-tier", "durable") and inferring a guarantee the
code does not make — the same file's docstring says faces have four tiers and
edges have two, and the edge tier is invariant under an edge growing in place,
not under the part changing size. A dimension edit is always the latter.
**A commit landing is not a product working, and a function being named
`durable` is not durability.** That is why every cell now carries a method,
and why `· source` is explicitly ranked below `· live app`.

### Freshness discipline

**The property that must hold:** a reader can tell a fresh row from a stale
one WITHOUT re-deriving it. Three parts now — the third added 2026-09-16,
because the first two are sound and did not catch that pass's worst row.

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

3. **A verdict can be false the day it is written, and parts 1 and 2 cannot
   see that.** Added 2026-09-16 after `Part modeling` was flipped ✅ on
   2026-09-15 and corrected ➖ on 2026-09-16 — twenty-four hours, no decay
   involved. Parts 1 and 2 grade the AGE of a row's evidence. Nothing graded
   its DEPTH, so a row derived by reading a function's name scored the same
   as one derived by driving the product. The `· <method>` field defined
   above is the fix, and the ranking is the whole of it: **`· live app`
   beats `· source` beats `· churn-only`, and only the first can support a
   claim about what the product does.**

**The mechanical check — BUILT AND SHIPPED as
`scripts/check-scorecard-freshness.py`** (stdlib + `git`, no daemon, no
network; `--warn-only` in `just lint`, hard `--self-test`, deliberately NOT a
CI gate). Run it as the **first step of every vision-steward cycle**, before
reading a single row. It parses BOTH tables out of this file — the scorecard
and the map below — so the territories cannot drift from the doc every agent
actually reads.

For each scorecard row it parses the Dimension name and the cited
`Re-derived … @ <sha>` (rows marked `PENDING` are exempt — there is no
citation to go stale, which is precisely why an unbounded `PENDING` is a
self-granted permanent exemption; see the bound above). The map of Dimension
→ territory paths is hand-maintained here, in the same shape a builder's
brief would name:

| Dimension | Territory (globs) |
|---|---|
| Sketching & constraints | `services/geometry/src/geometry/sketch/**`, `apps/web/src/sketch/**` |
| Part modeling | `services/geometry/src/geometry/{features,kernel}/**`, `packages/loft-wire/src/loft_wire/features.py`, `apps/web/src/routes/PartPage.tsx`, `apps/web/src/components/{HoleEditor,SketchStrip,CreateStrip,ExportToolGroup}.tsx` |
| Assemblies & mates | `services/documents/src/documents/assemblies.py`, `services/geometry/src/geometry/assembly/**`, `apps/web/src/assembly/**`, `apps/web/src/viewport/AssemblyScene.tsx` |
| Interop | `services/geometry/src/geometry/kernel/export.py`, `**/import_step.py` |
| Drawings & documentation | `services/geometry/src/geometry/drawings/**`, `apps/web/src/drawing*/**` |
| Sheet metal | `services/geometry/src/geometry/sheet_metal/**` |
| Selection & picking | `apps/web/src/viewport/{EdgePickOverlay,FacePickOverlay,ShellFaceOverlay,HolePointOverlay,PickMark,MeasureOverlay}.tsx`, `apps/web/src/measure/**` |
| Extensibility | `packages/loft-script/**` |
| Workspace & document management | `apps/web/src/routes/PartsPage.tsx`, `apps/web/src/api/parts.ts` |
| Performance on real parts | `docs/PERF.md`, `docs/GEOMETRY-QA.md`, `scripts/gauntlet.py`, `services/geometry/goldens-gauntlet/**`, `services/geometry/tests/test_benchmarks.py` |
| Free & unlimited / Your data, your files | `docs/AUDIT-ENGINEERING.md`, `deploy/**`, `LICENSE` |

**Two territory gaps were found and closed this pass, and the first one is a
trap worth naming: A PACKAGING REFACTOR CAN MOVE CODE OUT OF A ROW'S
TERRITORY, SILENTLY NARROWING WHAT THE GATE WATCHES.** `EdgeSignature` — the
type whose absolute-world-coordinate fields are the entire mechanism behind
the `Part modeling` correction above — now lives in
`packages/loft-wire/src/loft_wire/features.py`, because `14f6e14` split the
wire types into their own distribution. The Part modeling territory named
`services/geometry/**` and nothing else, so from that commit onward the gate
was watching the consumer and not the definition. Nothing errored: the
territory still matched plenty of tracked files, so it was not vacuous, just
**quietly smaller** — the failure mode a count floor cannot see. Added.
(Second gap, same shape: the `Performance` row's evidence is now
`docs/GEOMETRY-QA.md` and `scripts/gauntlet.py`, neither of which was
watched, so a gauntlet re-run could not have made the row stale. Added.)
**Whenever code MOVES, check whether it moved out of a territory — the gate
cannot tell you, because the paths it was given still resolve.**

**Unmapped rows, and why that is not a shrug.** `Collaboration &
versioning` and `Agent access (MCP)` have no territory because they have no
surface — nothing to watch yet. That is sanctioned, and the gate reports
them as `UNMAPPED` on every run precisely so a NEW unmapped row is visible
rather than quietly unwatched. But understand what the exemption costs: **an
unmapped row is watched by nothing and can therefore never be reported
stale — it is forever fresh by construction**, which is the same shape as
the unbounded `PENDING`. So: **add a territory the day a row's surface first
ships.** `Extensibility` was unmapped until this pass and is mapped now,
because `packages/loft-script` landed. A territory glob matching no tracked
file is an `ERROR`, not a placeholder — do not pre-register phantom paths for
Collaboration or MCP; register them on the day the code exists.

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

**What this gate CANNOT catch, measured 2026-09-16 — read this before
trusting a FRESH row.** The `Part modeling` ✅ that the 2026-09-16 product
audit falsified would **not** have been caught by this check, and it is worth
being exact about why rather than treating the miss as a bug:

- The gate compares the AGE of a row's evidence against churn in its
  territory. This row's evidence was **one day old** and its verdict was
  **already false** — there was no decay to detect. It did in fact report
  STALE that morning, but only incidentally, on an unrelated commit
  (`f7cd483`, adaptive volume integration); had that commit not landed the
  row would have read FRESH while being wrong.
- Conversely, it flagged four rows STALE whose verdicts a packaging refactor
  could not possibly have changed. **Both errors at once: a false negative on
  the row that mattered and four false positives on rows that did not.**

That is not a defect in the gate, it is its domain. **Decay and
mis-derivation are two different failures and need two different controls:**
the gate is the control for decay, and the `· <method>` field is the control
for mis-derivation. A gate that fires on churn will always be noisy in a repo
that refactors, and a row can be wrong without anything changing at all.

The practical rule that falls out of this, and it is the one to carry
forward: **a `STALE` line means re-derive; a `FRESH` line means nothing about
whether the verdict is true.** Read the method field to learn that. If a
row's deepest check is `· source` or `· churn-only`, the honest answer to
"does the product do this?" is *nobody has looked*.

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
