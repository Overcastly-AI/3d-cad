# Changelog archive

Full-detail changelog entries pruned from `docs/BACKLOG.md`'s "Changelog"
section each grooming pass (one-line-per-entry there; detail preserved
here). Newest first. Evidence for shipped items also lives in the Done
archive (`BACKLOG.md`) and per-item commits.

## 2026-08-21 to 2026-08-22 (Scorecard-gaps notes, pruned from BACKLOG.md pass 11 — superseded by pass 11's own note)

- **Groom pass 10 (2026-08-22) — SOLVE-1 SHIPPED (`7183955`).** Root cause:
  DogLeg starting from CURRENT positions is not the same as leaving free DOF
  alone — it walks a trajectory, so a value edit that only adds slack drags
  geometry the edit never named. `_GcsBuild.settle()` now pins every input
  coordinate the constraints still admit back to the author's value after
  convergence. Return deviation 2.162284 mm → 6.394885e-14 mm; bbox after
  the 8→12 edit `70×70×33.0795` (off-plane) → `70×70×30` (on-plane). A 245x
  perf regression in the rescued patch (11,050ms → 147ms) was found and
  fixed same-commit; goldens top out at 12 entities so no gate could have
  caught it. `docs/RESEARCH.md` §2/§9 corrected. SNAP-5 filed underneath it
  (line-by-line drawing never infers H/V). Correction filed against both
  audit docs: the "conflict path unreached on a value edit" claim did not
  survive measurement (status=conflicting reproduced on a pure value edit);
  R-5c was not a conflict, since no H/V was authored to contradict.
- **Groom pass 9 (2026-08-21) — two more audit passes recovered from the
  working tree, uncommitted, preserved first** (`3c82384`). SOLVE-1 and
  PICK-2 RE-SCOPED: SOLVE-1's real defect was a non-idempotent
  under-constrained solve (10→14→10 doesn't return); PICK-2's real cause
  was six pick-overlay queries gated on `meshGlbId !== null`, an empty
  surface not a raycast miss. Five new P0s from a sheet-metal fabrication-
  handoff pass: DXF-4 (flat-pattern drops every hole), DXF-5 ($INSUNITS
  wrong, 1000x), EDGEFLANGE-1 (flange off a thickness edge), MATE-1
  (mate face unreachable at any camera), NAME-2 (feature ref not
  re-stamped after a successful match). Vision-steward flagged (not yet
  actioned that pass): Sheet metal and Assemblies both ➖→❌ recommended; a
  new `Selection & direct manipulation` row recommended. Engineering audit
  pass 7/8: DOCTICK-GATE, PGTEST-GATE, K2 (P1), GATE-FLOOR (bumped P1),
  DEP-AUDIT filed; SPEC-9/SPEC-8 filed; 78 hours / 6 commits since the last
  line of product code flagged as the argument for that pass's dispatch.

## 2026-08-21 (groom pass 9 — SOLVE-1/PICK-2 RE-SCOPED before dispatch; second uncommitted audit doubled the P0 cluster)

- **Groom pass 9 (backlog-groomer):** preserved two more uncommitted audit
  passes (`3c82384`) — a sheet-metal fabrication-handoff product audit and
  an engineering pass that traced SOLVE-1/PICK-2 to source. **RE-SCOPED
  SOLVE-1 and PICK-2** (both tickets' original mechanisms were disproven by
  measurement; rewrote the fix and acceptance criteria for each — see
  tickets). Filed 5 new P0s from the fabrication job (DXF-4 flat-pattern
  drops all holes, DXF-5 wrong DXF units, 1000x; EDGEFLANGE-1 flange off a
  thickness edge; MATE-1 unreachable mate face; NAME-2 feature ref not
  re-stamped after match) + 7 P1s (SPEC-9 e2e race, ORTHO-1, HEM-1,
  MATEUI-1, LAYOUT-1, GHOST-1, STEPNAME-1) + smaller P2s (SPEC-8,
  AUDITOR-PORTS-1, SIGNIN-1, SM-POLISH-1 bucket). Corrected PGTEST-GATE's
  fix per the auditor's own retraction (CI likely already runs the 172
  tests; don't add a `services: postgres` block on the old claim); bumped
  GATE-FLOOR P2→P1 (reproduced unfixed twice) and PATTERN-1 P2→P1
  (corroborated twice, blocks the commonest pattern use). Top 3 dispatched
  this batch, fully disjoint: SOLVE-1 (kernel-architect, `sketch/**`),
  PICK-2 (frontend-builder, `PartPage.tsx`+`FacePickOverlay.tsx`), DXF-4
  (kernel-architect, `sheet_metal/**`+`drawings/flat_pattern.py`). Batch
  kind: **13 defect / 1 capability** (DOCTICK-GATE carries over from pass 8
  unbuilt; every NEW item this pass is a defect repair).

## 2026-08-17 (groom pass 7 — RECT-1/SNAP-2/SNAP-3/MIRROR-1 shipped; founder's file-page/export directive turned into 9 Ready tickets)

- **Groom pass 7 (backlog-groomer):** archived RECT-1/SNAP-2/SNAP-3/MIRROR-1
  shipped (all four `docs/AUDIT-PRODUCT.md`/`UI-REVIEW.md` 2026-08-17
  founder-directed audits — "the file page looks like an afterthought,"
  "export shouldn't live with mass properties") turned into 9 Ready tickets
  (EXPORT-1, REGISTER-1/2, VIEWCUBE-1, DXF-2a/2b/3, EXPORT-2, VISION-FIX-1)
  + 3 Next tickets (IMPORT-HEAL-1/2, EXPORT-ERR); ROADMAP "Current focus"
  corrected. 7 defect / 2 capability in the new Ready batch, kind-tagged
  per this pass's mandate. All 9 Ready tickets shipped by 2026-08-18 (see
  groom pass 8's Done archive entry, `docs/BACKLOG.md`) — but ZERO of the
  11 feature/fix commits that shipped them ticked ROADMAP/BACKLOG
  (`docs/AUDIT-ENGINEERING.md` Pass 7 M2), so pass 8 spent its first cycle
  on pure reconciliation before any new dispatch.

## 2026-08-16 (groom pass 6 — PICK-1/GEOM-3 shipped; vision-steward's competitive pass turned into build-ready tickets)

- **Groom pass 6 (backlog-groomer):** archived PICK-1 (`2b266b1`) + GEOM-3
  (`1e39c14`, geometry-qa PASS `0628ceb`) shipped; filed GQA-1 (P2)/GQA-2/
  GQA-3 (P3) from the geometry-qa pass. Turned the vision-steward's
  2026-08-16 competitive findings into build-ready tickets — RECT-1 (P0),
  SNAP-3 (P0), MIRROR-1 (P1), each verified against current HEAD by symbol,
  each `kind: capability` — closing the gap where COMPETITIVE.md/VISION.md
  prose could never reach the build loop's Ready queue. ROADMAP "Current
  focus" corrected (was still pointing at GEOM-3/PICK-1 as "next").

## 2026-08-15 (groom passes 4-5 — DIM-1 top-of-Ready, all four founder sketcher reports answered)

- **Groom pass 4 (backlog-groomer):** DIM-1 moved to top of Ready (QA
  `6df1170` found it writes silent WRONG geometry, not just a slow field);
  archived QA7-1/GEOM-2/FB-19 shipped, QA-VERIFY-1 closed; filed GEOM-3/4/5
  (GEOM-2's quantified honest limit + durable fix) and TOUCH-1 (no touch
  Playwright project).
- **Groom pass 5 (backlog-groomer):** all four founder 2026-08-01 sketcher
  reports now answered; archived DIM-1/SNAP-1/SKETCH-2 + the SKETCH-2
  follow-up fix (`8f00dec`, closes the blocking symmetric-datum bug +
  QA-SK2-1/2). Filed SNAP-2 (P0 — snap infers no constraint, silent drift on
  redrive), SKETCH-3, TOUCH-2, QA-SK2-3, SPEC-6/SPEC-7. Credited the
  mutation-marker CI gate (`56297d2`) with a Done entry it had none of.
  Wrongly concluded QAH-1 still open — corrected same evening.
- **Groom pass 5 correction (orchestrator-caught):** pass 5 searched only
  `a658db4..HEAD` (the brief's range) and found nothing touching QAH-1's
  assertion; the fix (`c3019b6`) is an ANCESTOR of `a658db4`, invisible to
  that window. **QAH-1 is CLOSED** — see BACKLOG Done archive for the
  evidence. Re-deriving from git log is only as good as the range it
  searches.

## 2026-08-14/15 (c449235 review triage + DIM-1/QA7-1/GEOM-2/FB-19 groom passes)

- **Groom pass 3 — c449235 review triage (backlog-groomer):** filed DIM-1
  (P0, dimension-field keystroke loss — the probable real founder bug),
  DIM-3/ESC-2/ESC-3 (armed-state flow + FB-13-class landmine + test gap),
  QAH-1 (P0, unfiled e2e CI-red cause) and QA-VERIFY-1/VP-1b; archived
  SKETCH-1/VP-1/VP-1a as shipped-unreviewed; renamed the FB-20 id collision
  to FLOW-1.
- **Groom pass 4 — DIM-1 QA / QA7-1 / GEOM-2 review / FB-19 reconciliation
  (backlog-groomer):** DIM-1 reclassified P0-top on independent QA finding
  silent wrong-geometry writes (`6df1170`); archived QA7-1/GEOM-2/FB-19 as
  shipped (all still owe review/QA/screenshot-send, tracked as QA7-1b/FB-19b);
  closed QA-VERIFY-1 (both specs now run green); filed GEOM-3 (P0, the
  quantified honest-limit/durable-fix ticket — `f >= 1 - 2r`, measured on a
  vented plate at r=40.7%), GEOM-4/GEOM-5 (smaller follow-ups), TOUCH-1 (no
  touch/mobile Playwright project has ever existed).

## 2026-08-14 (audit-driven groom passes 1-2, pre-c449235-review)

- **Groom + hygiene sweep (backlog-groomer):** Ready had grown to 145 items /
  ~2,850 lines (104 already shipped, sitting unarchived). Archived the 104,
  curated a 10-item Ready from two fresh audit passes (M1-22 product, K1-8
  engineering) plus founder reports. ROADMAP "Current focus" fixed (K6).
- **Groom pass 2 (backlog-groomer):** ticked K7 shipped (29387da); filed
  VP-1a (trackpad orbit — VP-1's stated gap) and SNAP-1 (founder "snap points
  not working," never previously reproduced), both queued behind the occupied
  `viewport/sketch` territories; pruned older Changelog entries into
  `docs/CHANGELOG.md`. Dispatched disjoint from live work (viewport/sketch/
  geometry occupied): QA7-1 (e2e wait fix) + FB-19 (chrome density).

## 2026-08-08 to 2026-08-11 (CI-4 fixes, SEL-4/6/6b)

- 2026-08-11 — CI-4 review fix (backend-builder): `--fail-on-flaky` guard
  matched its own text; flag literal now assembled in pieces, 3 probes, 4
  mutations verified (`aea990a`).
- 2026-08-11 — CI-4 frontend slice (frontend-builder): `waitForRenders`
  counts r3f renders, throws with count achieved; `sketch-visibility` ink=0
  reproduced 5/10 locally, an AA phase lottery not a regression (SPEC-4).
- 2026-08-11 — SEL-6/6b independent QA verdict: PASS (qa-tester) — occluded
  plate 94.8% with occluder hidden (was 8.5%), names near face; 5 mutations
  red.
- 2026-08-08 — SEL-6b (frontend-builder): `hiddenPicks.ts` withholds a
  hidden body's edges/faces/snap points; 24 edge marks -> 12, 12 face -> 6.
- 2026-08-08 — SEL-6 (frontend-builder): `pickRaycast.ts` filters hidden
  triangles; shell reachability with wall hidden 7.4% -> 96.3%.
- 2026-08-08 — SEL-4 independent QA verdict: PASS (qa-tester) — 25 e2e green,
  10 checks the shipped gate didn't express (draft, refusals, recede, touch).
- 2026-08-08 — SEL-4 review follow-up (frontend-builder): hidden body stops
  occluding edge band; mate picks 8.9% -> ≥50%; one owner for mate hover.
- 2026-08-08 — SEL-4 (5/5) dense-hole gate (frontend-builder): anisotropy not
  area for edges, mutation-verified on all three conversions.
- 2026-08-08 — SEL-4 (4/5) drill anywhere on the face (frontend-builder):
  free placement by raycast + plane projection.
- 2026-08-08 — SEL-4 (3/5) shell/draft/mates address geometry
  (frontend-builder): surface raycast + edge band; shell reachability
  1.7% -> 95.6%.
- 2026-08-08 — SEL-4 (2/5) fillet/chamfer/measure pick the edge
  (frontend-builder): 24px screen-space corridor with occlusion test.
- 2026-08-08 — SEL-4 (1/5) one pick hit-test, shared (frontend-builder):
  `PickSurface`/`FacePatch`/`useViewportPickStamp`/`edgeBand` extracted.

## 2026-07-22 to 2026-08-01 (Escape/select rework, drill-anywhere, drawing
re-anchoring, concurrency, observability, mirror/hole/assembly-import
features, sheet-metal fold-back, groom passes)

- 2026-08-01 — **Escape no longer ends your sketch, and a click no longer piles
  up (frontend-builder):** FB-13/FB-14 — the cascade unwinds and then stops (it
  still backs out of a sketch holding no work); plain click replaces, Shift or
  Ctrl/Cmd adds. `e2e/sketch-escape-select.spec.ts` is red on the old behaviour.
- 2026-08-01 — **You can drill where you want (frontend-builder):** QA3-1 —
  numeric X/Y in the picked face's STATED frame, a per-keystroke material check
  that names the opening you are in, and concentric snaps to every circular edge
  on the face.
- 2026-08-01 — **Dogfooding pass #3, the imported-STEP remix (qa-tester):** a
  NEMA 17 vendor plate imported, remixed and re-revved through the real stack.
  Seven closed-form comparisons exact (rev-B/rev-C swaps re-anchored five
  downstream features to 12 s.f.); six defects filed QA3-1..6, two P1 —
  you cannot drill where you want, and a sketch on an imported face has no
  reference to the import (measured: a 0.065111070 mm eccentric register).
- 2026-08-01 — **The drawing says on screen what it said on the print
  (frontend-builder):** N1/N2's frontend half — a sheet check strip for
  `layout_issues` (with the Auto-place that fixes each pair), a RE-ANCHORED badge
  + one-click Confirm for a `durable` anchor, and the typed reason beside an
  unresolved dimension. e2e resizes a dimensioned part and reads 120.000 in-app.
- 2026-08-01 — **CONC-1/2/3: more than one person can use it now
  (backend-builder):** gateway session affinity over a comma-separated
  `GEOMETRY_URL` (sticky 30.6 s vs random 64.9 s wall, hit 0.40 vs 0.10), a
  bounded FIFO admission queue on the OCCT routes (0 of 16 -> 11 of 16 delivered
  inside a 30 s deadline), and a timeout that says 504 "still working" instead
  of 502 "unreachable". `docs/OPERATIONS.md` §6.
- 2026-08-01 — **GATE-1: CI drives a browser now (platform-builder):** the full
  Playwright suite on every code push, sharded 4 ways, with a reconcile job that
  fails unless the shards covered `playwright test --list` exactly once. Proven
  by pushing the stale assertion back and watching CI reject it.
- 2026-07-31 — **OBS-1: the stack can be watched (backend-builder):** Prometheus
  `/metrics` from py-kit for all three services — rebuild histogram by cache ×
  tree size, cache hit rate, feature errors by code, STEP refusals; +30 µs/req
  measured; fail-closed outside dev. `docs/OBSERVABILITY.md`.
- 2026-07-31 — **UI-W2 part half + the two framing defects (frontend-builder):**
  Origin / Sketches / Bodies get the assembly's eye vocabulary; origin planes and
  axes render for the first time; "Fit model" frames the unobstructed rect at a
  distance solved from the part's real projection, and the ViewCube clears its
  own corner. Asserted on canvas pixels, mutation-verified.
- 2026-07-31 — **What LEAVES the tool now says what it is (kernel-architect):**
  audit N8 — an assembly STEP instances its parts (21 instances / 2 parts:
  21 B-reps + 504 KB -> **2 B-reps + 58 KB**; `located()` was a deep geometric
  copy, so no writer could see the instancing); N4 — part/assembly exports are
  named after the document in both the filename and the PRODUCT, and
  `assembly.step` no longer overwrites itself; #50 — the tapped-hole callout
  reaches SVG/PDF/DXF; N5 (part) — the exported page is white, not grey.
- 2026-07-31 — **Three surfaces stopped over-claiming, and settings exist
  (frontend-builder, 2026-07-31):** the register no longer calls a rolled-back
  prefix "Clean" (J3b), the assembly panel earns the words COMBINED MASS (and can
  finally compute one — the browser never sent the parts' materials), a lost
  dimension prints its reason on the sheet as well as in the export (QA-4b), and
  `/settings` ships with five wired rows including invert-scroll.
- 2026-07-30 — **The drawing survives the revision (kernel-architect):** audit N1 —
  edges get the two-tier resolver faces have (`drawings/anchor.py`) so a widened
  plate's dimension re-measures 120.000 instead of dying; N2 — iso anchors clear by
  construction (24 mm at any size) and a colliding sheet stamps a banner, never
  exports silently. (Ready-queue entries for both landed early in `3f5fc98`, which
  swept this agent's in-flight BACKLOG hunks.)
- 2026-07-30 — **UI-W1 bottom timeline (frontend-builder):** rollback is now a
  docked machine way with a draggable/keyboard travel stop, verb-glyph op chips and
  a dashed way past the stop; one shared `VERB_GLYPHS` map serves band + timeline.
- 2026-07-30 — **UI-W3/W4 pre-selection + pinned references (frontend-builder):**
  a viewport pick outlives its command and seeds the next one (hole/datum/sketch/
  shell/draft/fillet/chamfer), the hole's face pick arms on open, and its
  references sit in a pinned anchor block on the right rail. UI-REVIEW P1 (export
  strip under the fold) fixed by pinning it, not by trimming copy.
- 2026-07-30 — **UI-W2 visibility/opacity/isolate, assembly half (frontend-builder):**
  every component row gets an eye, the addressed one a SOLID · GHOST · HIDE control,
  isolate a right-click verb with `V`/`⇧V` and an `ISOLATED` stamp as the way back.
  Asserted on canvas PIXELS, not aria state (mandate 3c).
- 2026-07-31 — **UI-W5 entity snapping (frontend-builder):** endpoint / midpoint /
  centre / intersection / tangent / perpendicular snap by default; Ctrl-Cmd
  SUPPRESSES (inverted on purpose), Shift axis-locks, `G` still owns the grid.
  A named mark says which snap you get before the click.
- 2026-07-30 — **Last-evaluate record on the part row (backend-builder):**
  migration `0012` + derived `eval_state` (`never`/`ok`/`failed`/`stale`), written
  by the gateway post-evaluate; staleness derived from `tree_version`, not guessed.
- 2026-07-25 — **Tapped-hole authoring (frontend-builder):** `Tapped` checkbox +
  ISO designation picker in `HoleEditor` derives the tap drill without locking
  it; the tree row carries `hole · M10x1.5` — the only place a tap is visible.
- 2026-07-25 — **TAPPED holes, cosmetic threads (kernel-architect):** `thread:
  IsoMetricThread | None` on `HoleParamsV1` cuts the ISO tap drill `D - P` and
  carries the callout; typed `hole_thread_unsupported`/`hole_thread_mismatch`.
- 2026-07-25 — **jsdom component-test tier (frontend-builder):** `apps/web` +
  `packages/design` now run two vitest projects (`*.test.ts` node, `*.test.tsx`
  jsdom+Testing Library); 46 tests pin the three burn-down UI defects. 882 web.
- 2026-07-25 — **Burn-down code-review fixes, frontend (frontend-builder):**
  right-drag pan no longer opens the viewport context menu (click-slop gate,
  press- and release-fired `contextmenu`); the extrude ghost honours
  `operation` (cut = cold dark void, not a brass solid); the assembly inspector
  and readout precision are unit-aware; `ContextMenu` restores focus on close.
- 2026-07-24 — **Drawings #4 SLICE 2 — gateway gate-removal + documents resolution
  (backend-builder):** `assembly_views_unsupported` gone; documents
  `GET /assemblies/{id}/evaluation-request` resolves the graph; gateway threads it as
  additive `ComposeDrawingRequest.assembly`. Geometry compose branch next (Ready).
- 2026-07-23 — **Mirror feature WEB AUTHORING (frontend-builder):** Modify-band
  Mirror command (shortcut I) + `MirrorEditor` in the shared editor seat, reusing
  the sketch/section plane picker (origin XY/XZ/YZ radios + datum FeatureRef);
  `mirror` added to frontend `BODY_AFFECTING_FEATURE_TYPES` + drift guard;
  `friendlyFeatureError` gains the mirror codes; e2e `mirror.spec.ts` mirrors a
  real body (Z-extent + volume double about XY, `MirrorN` Solved). Mirror is now
  end-to-end.
- 2026-07-23 — **Mirror feature GEOMETRY + DTO (kernel-architect):**
  `MirrorFeature`/`MirrorParamsV1` reflect the current body about a plane (origin
  datum or `datum` feature — the SAME `GeomRef` a sketch uses) and union the
  reflection in (pattern semantics; disjoint reflection → valid 2-lump body).
  Golden `mirror-triangle-prism-2x` (analytic 2V + centroid-on-plane reflection
  proof), typed degradation, wired across every feature-registry arm. Web-authoring
  slice remains.
- 2026-07-23 — **Assembly import response-amplification DoS CLOSED
  (kernel-architect):** bounded the untrusted parse's OUTPUT at the geometry
  source — occurrence-count cap aborts the walk in the CPU-bounded child
  (`import_too_many_products`), total-`body_step`-byte cap (32 MiB) rejects a big
  body instanced many times before materialisation (`import_response_too_large`);
  both typed 422s. Filed P2 follow-ups: body_step-once-per-id reshape + permanent
  3-service integration test.
- 2026-07-23 — **Assembly STEP import SLICE 2a — reader hardened + editable body
  (kernel-architect):** DoS parse-bound WIRED to the XCAF reader (untrusted
  `ReadFile`/`Transfer` + walk now in the single-body reader's killable
  `RLIMIT_CPU` + wall-clock subprocess → `import_parse_timeout`); walk/tessellate/
  measure/export phase guarded (degenerate-but-transferable solid → typed 422, not
  a raw 500); `ImportedProduct` gains `body_step` (LOCAL-frame STEP fragment the
  single-body `import` feature ingests verbatim) + `body_step_id` (content-address
  dedup key). Slice 2b (documents assembly creation + gateway upload) can now land
  on a proven-safe reader.
- 2026-07-23 — **Dedicated Hole feature SLICE 1 (kernel-architect):** first-class
  `HoleFeature`/`HoleParamsV1` (face `SubshapeRef` + world point + diameter +
  through-all|blind) wired across every registry arm + `kernel/hole.py`
  (`bore_hole`, auto inward cut direction); golden `hole-through-r5-40x25x10`
  proves analytic volume parity (10000−250π) AND sketch+extrude-cut parity; typed
  degradation (`hole_off_body`/`hole_too_deep`). Slice 2 (counterbore/countersink/
  tapped + drill tables) + web authoring remain.
- 2026-07-23 — **Hole SLICE 1 WEB authoring (frontend-builder):** Hole command
  (Modify band + `O`) → `HoleEditor`; face pick REUSES `FacePickOverlay`, point
  pick REUSES the measure `PickNode` affordance (`HolePointOverlay` — centre +
  coplanar corners), Ø + through-all|blind. Typed rebuild errors → guidance
  (`friendlyFeatureError`). e2e drills through-all + blind in the UI; 13 units.
  Hole slice 1 is now end-to-end; slice 2 (counterbore/countersink) remains.
- 2026-07-23 — **Assembly STEP import SLICE 1 — geometry XCAF reader
  (kernel-architect):** `POST /api/v1/assembly/import` + `kernel/step_assembly.py`
  (XDE `STEPCAFControl_Reader` walk, mirror of the export composer) →
  `StepAssemblyImportResult{has_assembly_structure, products}`; export↔import
  round-trip recovers N products/placements/PRODUCT-names (off-axis rotation +
  repeated part), flat STEP → false-flag (MB-4b path intact). Slice 2 (documents
  assembly creation + gateway upload + fallback wiring) remains.
- 2026-07-23 — **E1a — Section views END-TO-END wire (kernel-architect):**
  per-view `section_params` map (`dict[int, SectionViewParams]`) on the geometry
  evaluate/compose wire; gateway `_compose_request` threads each persisted view's
  datum; geometry end-to-end + gateway-threading guard tests; E1b (web authoring)
  deferred. Non-section sheets byte-identical.
- 2026-07-23 — **Groom + restock (backlog-groomer):** reconciled BACKLOG +
  ROADMAP against `a6a5814..0ed9f74` (18 Ready items archived as one-liners);
  formalized the fresh product-audit findings into 3 P0/P1 assembly-interop
  Ready items + Hole/suppress/mirror P2 items; marked section-views v1 IN
  FLIGHT (kernel-architect, uncommitted); pruned pre-07-22 entries here into
  `CHANGELOG.md`.
- 2026-07-23 — **Product audit — "the assembly is a one-way street":** a
  bolted assembly builds+solves but has no STEP export, no interference
  check, no product-structure import; filed as the new P0/P1 Ready trio.
  Also named suppress/mirror/dedicated-Hole as the top everyday-ergonomics gaps.
- 2026-07-23 — **Drawings dead-capability drain (D1-D4) + engineering-audit
  sweep:** title-block, first-angle, dimension-placement, and the
  assembly-view 404 all wired/gated; sweep found 6 orphans total (D1-D6),
  D5/D6 + the process-guard tail remain.
- 2026-07-23 — **Drawings note-render, DE-4 artifact cache, sheet-size
  picker, MB-4c wire/frontend tail, e2e hardening** (raster-format fix +
  CPU-contention timeouts) — see Done archive for one-liners.
- 2026-07-22 — **WF-1 fold-back coaxial fix (kernel-architect, code review):**
  fold-back invariant now measures each bend FACE once (dedup by identity,
  `resolve.live_bend_face_widths`) + `find_cylindrical_face` disambiguates by span;
  two coaxial equal-radius flanges on collinear segments develop instead of
  false-rejecting. Golden `coaxial-two-segment-flange-unfold`; §5 note corrected.
- 2026-07-22 — **WF-1 layer 2 + PB-1 (kernel-architect):** edge-flange width
  extents (`width_mm`/`offset_mm`) + auto bend-end relief + partial-width
  development (design §4.5); founder 50×50-flange case golden-gated; PB-1 fell out.
- 2026-07-22 — **WF-1 layer 1 (kernel-architect):** runtime fold-back invariant
  in `unfold_sheet_metal` — live coaxial bend widths vs developed fold widths;
  cut-after-fold now typed-rejects. Goldens byte-unchanged; layer 2 stays open.
- 2026-07-22 — **Founder dogfooding — WF-1 (50-wide flange on a 100 mm edge
  via fold-then-trim):** 3D exact; flat pattern SILENTLY WRONG (full-width
  blank, no error) — the first dishonest failure found. Filed P0 (runtime
  fold-back invariant → typed reject, then trimmed/width-extent development).
- 2026-07-22 — **Founder dogfooding — PB-1 (partial folds + viewport
  rotation):** 3 fold widths (70 partial / 200 / 120) on a notched base — 3D
  exact to closed form; flat pattern typed-rejects (filed P2, matrix row
  upgraded). Snap views, real-pointer orbit, pick-after-rotate all pass.

## 2026-07-19 to 2026-07-20 (sheet-metal v2 + corner relief + hem v1 +
STEP hardening + WB-64/TB-1 dogfooding)

- **Sheet-metal CLOSED HEM (kernel-architect):** first-class `sheet_metal_hem`
  feature — a fixed 180° fold reusing `build_edge_flange` + the shipped unfold
  verbatim. Finding: the near-flat fold cannot self-intersect (return sits
  ~2·radius above base), so it's one clean valid solid, no guard. Golden
  `closed-hem-plate`; existing goldens byte-unchanged. Open/teardrop/rolled +
  a Hem UI deferred.
- **Sheet-metal CORNER RELIEF v1 (kernel-architect):** reconciled + finished
  container-restart-stranded work (`_Rect` defined after first use → import
  `NameError`; 12 ruff errors — cleared). `apply_corner_relief` cuts the
  rectangular 3D notch; `unfold_sheet_metal(reliefs=...)` develops the
  relieved depth-1 tray (reentrant notch, area conservation,
  byte-deterministic). Golden `corner-tray-relieved-unfold` + 12 tests; all
  depth-1/2 goldens byte-unchanged.
- **Sheet-metal depth-≥2 bend-TREE unfold FEATURE (kernel-architect):** spike
  graduated into `unfold_sheet_metal`; depth-2 (box corner / return / Z) now
  unfolds to ONE union outline, self-overlap → typed `UnfoldOverlapError`.
  Depth-1 goldens byte-identical; new `bend-chain-{corner,parallel}-unfold`;
  spike retired.
- **Sheet-metal depth-≥2 bend-chain unfold SPIKE (kernel-architect):**
  VERDICT **TRACTABLE, no wall.** Recursive-compositional tree walk unfolds a
  box corner (flange off a flange) — each child placed in its parent's
  already-flattened frame; BA-strip residual ~3e-15, isometry residual 0.0,
  exact area conservation, byte-deterministic. Isolated `_spike_bend_chain.py`
  + 2 goldens (perp corner + parallel chain); shipped depth-1 unfold
  byte-unchanged. Follow-on feature slices named in design §4.3.
- **Sheet-metal depth-2 no-crash + N=4 pan golden (kernel-architect):**
  code-review follow-up on the non-parallel unfold. Author-reachable depth-2
  bodies (flange off a flange) now raise a UNIFORM typed `UnfoldStarError`
  before the layout — the perpendicular box corner no longer leaks a raw
  kernel `Standard_ConstructionError`; plus-pattern assembler guards its
  full-width closed-loop assumption; `BendLine.flat_start/end` 2D-frame
  semantics documented; new `pan-four-flange-perp-unfold` golden. Parallel
  goldens byte-identical.
- **Sheet metal v2 #1 — non-parallel bend stars (kernel-architect):** spike
  proved the 2D plus/cross layout tractable (shared corners included —
  disjoint arms, exactly-additive volume). `unfold_sheet_metal` branches
  parallel (byte-identical 1D strip) vs non-parallel (2D tray); new
  `corner-tray-perp-unfold` golden + narrowed `UnfoldStarError`. Full
  geometry suite green.
- **STEP parse-timeout hardened (kernel-architect):** wall-clock bound →
  CPU-time ceiling (`RLIMIT_CPU`, default 20 s) + wall-clock liveness backstop
  (default 60 s); kills the CPU-contention false-fire flake while preserving
  the DoS guard. Full geometry suite green; flaky tests 8× clean under 2× CPU
  oversubscription. No contract change.
- **Groom + restock (backlog-groomer, 2026-07-19):** reconciled BACKLOG +
  ROADMAP against `36dc3d9..a6a5814` (six converged pillars: Assemblies,
  Drawings+export, Multi-body, Units, Undo/redo, Sheet metal); archived ~950
  lines of shipped items to one-liners, backfilled two missing CHANGELOG.md
  batches, fixed 5 stale ROADMAP phase/sub-item markers, closed two stale
  unchecked duplicate items (already shipped) and two stale Next items
  superseded by shipped pillars. Restocked Ready with 9 items.
- **Founder dogfooding pass #2 — TB-1 site toolbox (all queued scenarios, one
  assembly, 2026-07-20):** tray (4 walls + 2 hems + 4 reliefs — first
  coexistence, 12 features OK), pattern ×4 (exact to 0.01 mm³), spline-loft
  grip, 8-instance assembly + BOM, authz probes clean. ONE new kernel finding:
  hem-on-flange-top can't flat-pattern (typed reject, filed P2).
- **Drawings auto-layout FIT-SCALE (from WB-64 findings, 2026-07-20):**
  `fitScale` picks the largest standard scale fitting the quadrant cells
  (user's pick = ceiling); 6 unit cases, drawings e2e green. Sheet-size
  select + flat-pattern fit remain (P3). Retro items filed: Drawings parity
  campaign (P1), dead-capability sweep, recurring dogfooding gate, threads.
- **Founder dogfooding — WB-64 64 oz bottle (full product pass, 2026-07-20):**
  bottle/cap/assembly/GA modeled + verified in-app (cavity kernel-vs-analytic
  Δ=2 mm³ in 2.11 L); 3 drawing findings filed (Ready), no geometry defects.

## 2026-07-12 (post product+engineering audit batch)

- **Multi-loop closed profiles → holes shipped** (`a36e436`, product audit's
  #1 gap). `build_profile_face` (kernel/extrude.py, shared by
  extrude/revolve/sweep/loft) classifies the largest-area loop as the outer
  boundary, the rest as interior holes → `Face(outer, inner_wires)`; no
  topological naming needed. v1: one outer boundary + disjoint strictly
  interior holes; disjoint/crossing/overlapping/nested loops →
  `profile_unsupported`, open loop → `profile_not_closed`. Golden
  `sketch-extrude-plate-2holes-40x25x10` (analytic V, 8 faces, STEP
  round-trip + restart determinism). [kernel-architect]
- **F3 doc-defect fixed** (`c9abf7e`) — `loft.py`'s module note still said
  offset planes were unauthorable after `df308e4` landed them; synced.
  [kernel-architect]
- **#8b Loft authoring UI shipped.** Ordered section-stack picker (≥2 sketch
  sections, add/remove/reorder — order is the blend sequence) with a "blend
  spine" signature, Add/Cut, `L` accelerator, honest v1 note; DRY
  `LoftParamsV1` from `@loft/ts-client`. e2e (real stack): two parallel
  circles (XY + XY+30 via "+ Offset plane") → a rendered frustum in the tree;
  submit guard on incomplete stacks. Closes #8. [frontend-builder]
- **#2b offset/datum-plane picker UI shipped.** One-click origin planes
  preserved; inline "+ Offset plane" + standalone Datum tool create a
  `datum` feature the sketch seats on via `FeatureRef`. `plane.ts`
  generalized to a placed `PlaneBasis` (one plane-math source, DOM+WebGL).
  e2e proof: XY+30 sketch→extrude → body bbox z≈30..40. #8b loft UI now
  fully unblocked. [frontend-builder]
- **Offset/datum planes — BACKEND shipped.** `DatumFeature` in the Feature
  union + registry; sketch-on-datum via the widened `FeatureRef` plane slot;
  `resolve_sketch_plane` DRY funnel → resolved `Plane`. Goldens: offset
  extrude + the two-parallel-circles→cylinder loft. Ready #2 backend done;
  #8b loft UI unblocked; #2b plane-picker UI is follow-up. [kernel-architect]
- **Datum-planes design note landed** (`docs/design/datum-planes.md`):
  datum-plane-as-feature (vs inline spec); v1 = offset-from-origin-datum by
  signed distance; additive backward-compat (no `param_version` bump). Ticks
  Ready #1; unblocks #2 impl + #8b loft UI. [kernel-architect]
- **Groomed after the sketch-cluster + sweep/loft-backend batch.** Archived
  8 shipped items (session-tool cluster, sweep, loft backend); restocked
  Ready with offset/datum planes (design note + implementation, ranked top —
  unblocks #8b loft UI), face/edge picking, and 3 sketch-polish items; #8b
  explicitly marked blocked. [backlog-groomer]

## 2026-07-12

- **Loft (#8) BACKEND shipped.** `LoftFeature`/`LoftParamsV1` (`profiles:
  FeatureRef[]` min 2 + add/cut), `build_loft_section`/`loft_sections` ruled
  `make_loft`, evaluate-tree handler. Sections = closed wire OR single apex
  point (loft-to-a-point). Golden `loft-pyramid-sq20-h30` (analytic pyramid
  4000 mm³) through every gate. Apex support unblocks an analytic golden
  (parallel offset sections need offset datum planes). #8b (UI) queued,
  later marked blocked on offset/datum planes. [kernel-architect]
- **Sketch fillet/chamfer (#5) BACKEND shipped.** `POST /api/v1/
  sketch/{fillet,chamfer}` (gateway-proxied): exact closed-form corner
  round/bevel — both lines trimmed to their tangent/setback points, arc/line
  bridge appended (fresh `f"{a}.{n}"` id). v1 line-line only (line-arc/
  arc-arc deferred). Also hardened `_mirror_entity` dispatch with
  `assert_never`. #5b (UI) queued. [kernel-architect]
- **Sketch mirror (#4) BACKEND shipped.** `POST /api/v1/sketch/mirror`
  (gateway-proxied): exact analytic reflection of point/line/circle/arc
  about a line-entity-id OR two-point axis; arc CCW-swap preserves the
  invariant. #4b (UI) queued. [kernel-architect]
- **Ready #1 (Fillet/Chamfer authoring UI) shipped** + reopened #6 P1
  fixed: measure pick-marks now hit-test by real click/tap (edge marks at
  true midpoint, vertex z-priority, visible reticle nodes). [frontend-builder]
- **Groomed for Phase 2 restock.** Ready batch 1 (7 items: topological
  naming, construction geometry, 6-constraint vocabulary, revolve,
  measurement, pattern) archived; older changelog entries moved to
  `CHANGELOG.md`. New 10-item Ready queue from `docs/COMPETITIVE.md`'s first
  discovery pass + a code-inspection finding (Fillet/Chamfer buttons wired
  but never connected — `PartPage` never passes `onFillet`/`onChamfer`).
  [backlog-groomer]
- **2026-08-21 — Groom pass 8 (backlog-groomer):** reconciled 10 shipped-
  but-unticked tickets (pass 7's export cluster, `docs/AUDIT-ENGINEERING.md`
  Pass 7 M2 found 0/27 commits ticked ROADMAP/BACKLOG) into Done; filed
  DOCTICK-GATE to close the hole. New P0 cluster from the fresh "rotational
  part" audit — SOLVE-1 (silently wrong geometry on a conflicting dimension
  edit) + PICK-2 (inert repair button) — outranks the standing FB-21/FB-9
  frame-convention P0s. 6 new engineering tickets from the same audit round
  (DOCTICK-GATE, PGTEST-GATE, K2 bumped P1, GATE-FLOOR, DEP-AUDIT, plus 2 P3
  housekeeping items). Top 3 dispatched: SOLVE-1 (kernel-architect), PICK-2
  (frontend-builder), DOCTICK-GATE (platform-builder). Batch kind split:
  2 defect / 1 capability.
