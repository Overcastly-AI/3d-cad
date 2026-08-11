# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`,
and the roadmap. The autonomous build loop pulls from **Ready (top of
queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication.

- **✅ rows:** Sketching, Part modeling, Price/freedom.
- **➖ rows (usable, short of incumbent parity):** **Assemblies — headline gap
  is now "one-way street"** (fresh product-audit pass 2026-07-23): you can
  build+solve a bolted assembly, now **export it (assembly STEP, AP214
  product structure — shipped 2026-07-23)** and **check it fits (interference/
  collision detection — shipped 2026-07-23)**, but you cannot bring one in (no
  assembly-STEP import/product-structure) — also still no exploded views,
  recursive BOM, part-version pinning. Interop (STEP two-way is real for a *part*; assembly
  STEP **export** now real, **import** still missing — the one-way gap narrowed
  to inbound-only). Drawings (dead-capability drain
  mostly closed this batch — title-block/first-angle/dimension-placement/notes
  all wired; section views now FULLY END-TO-END (E1a wire 2026-07-23 + E1b web
  authoring 2026-07-23 — the `SectionAuthorPanel` picks a cutting plane + flip
  in-app, persists per-view `section_params`, and the sheet composes + hatches
  on-screen; a working engineer cuts a section without touching the API); still
  no detail views, assembly views/BOM/balloons, GD&T). Sheet
  metal (bend chains + corner relief + closed hem + edge-flange WIDTH EXTENTS
  + auto bend-end relief shipped, all click-authorable in-app; still no open/
  teardrop/rolled hems, miters, tabs, or gauge tables).
- **❌ rows (untouched, no design doc yet):** Performance — **the real-part
  corpus now EXISTS and has been measured** (`docs/PERF.md`, geometry-qa
  2026-07-31: the wall is ~50 features, unusable at 200; PERF-1..PERF-5 filed) —
  so the row is ❌ on *substance*, not on ignorance, and has a numbered fix list;
  Collaboration & versioning (Phase 3, unstarted), Extensibility/scripting + MCP
  (Phase 5, unstarted).
- **Stale VISION note (unchanged since last pass, still unfixed):** VISION's
  Interop row Notes still call "the untrusted-parse wall-clock/DoS bound" a
  tracked P1 fast-follow — closed twice over (`483d5ae` 2026-07-13 hard bound,
  `f5a9038` 2026-07-19 contention-invariant `RLIMIT_CPU`); flagged for the
  vision-steward to correct next re-score.
- **`docs/COMPETITIVE.md`** still dates from 2026-07-12 (+Sheet metal 07-17 +
  AEC/BIM scoping 07-19) — stale against Assemblies/Drawings/Multi-body and
  now against the fresh assembly-interop gaps below; flagged for the
  vision-steward to refresh. Ready queue restocked from BACKLOG-native audit
  findings this pass, not from COMPETITIVE.

## Ready (top of queue)

- [ ] (P2, S) **SEL-7 — hole placement is the one overlay that still drills
      into a body nobody can see** (`apps/web`). Filed 2026-08-08 by the
      orchestrator from the SEL-6 review (amber, confirmed real by the
      reviewer). SEL-6 closed the raycast half everywhere and SEL-6b closed the
      offer half for the marks, the band corridor and the FacePatch — but
      `HolePointOverlay.tsx:333` mounts its DOM snap nodes (`hole-point-center`,
      `-vertex-N`, `-circle-N`) and the datum crosshair on EDITOR state only
      (`PartPage.tsx:4474`), never on visibility. Its `PickSurface` is covered;
      the DOM buttons are not. Hide the body mid-command and diamonds float in
      empty air that still drills a real hole into geometry the user cannot see.
      Exactly the class SEL-6b named — "a PickNode is a DOM button that never
      asked the scene" — one overlay short of a clean sweep.
      FIX: gate the armed block on `useHiddenPicks().isHiddenFace(placementOrdinal)`,
      or `isHiddenPoint` per snap. The hook already exists; this is wiring.
      ACCEPTANCE: with the target body hidden, no hole-point DOM node is
      mounted and no crosshair is drawn; unhiding restores every one of them at
      its previous ordinal. Mutation-verify the gate goes red on today's code.
      [src: code-reviewer, SEL-6 slice 2026-08-08]

- [ ] (P3, XS) **SEL-8 — SEL-6 aftercare: five loose ends the review logged
      green** (`apps/web`). Filed 2026-08-08 by the orchestrator. None blocks
      anything; batched so they are fixed once rather than rediscovered five
      times. (a) `pickRaycast.ts:6` — the evidence numbers DISAGREE for the same
      pre-fix census: the commit message and `docs/ROADMAP.md` say 7.4% -> 96.3%
      (control 96.7%), the module header and `pick-affordance.spec.ts:601` say
      8.5% (27/317, control 98.0%). Probably pre/post the unlit luminance-proxy
      correction, but this repo's standard is measured numbers that AGREE — name
      the run each came from or reconcile them. (b) `ModelMesh.tsx:207` — a
      fifth copy of the stale reason survived the four-copy sweep; the comment
      still credits a pointer-handler refusal SEL-6 deleted, and the
      `!bodyFaceState.hidden.has(hoveredFace)` guard at :220 is now dead (
      harmless as defence-in-depth, but say so). (c) `hiddenPicks.ts:83` — every
      mounting overlay builds its own weld-bucket Map, so two live overlays mean
      duplicate O(V) passes with string allocation; free today via the
      OFFER_EVERYTHING short-circuit, but derive it once beside
      `pickHiddenFaces` in `partView.ts` if it shows on a heavy part.
      (d) `EdgePickOverlay.tsx:56` — `FacePickOverlay` drops its hover when the
      offer changes; `EdgePickOverlay`, `ShellFaceOverlay` and `MeasureOverlay`
      do not, so the QA stamps the e2e gates read can carry a withheld entity's
      index for one frame. Fails toward a false RED, so robustness only.
      (e) `partView.ts:163` — only `hidden` feeds `pickHiddenFaces`, so a
      GHOSTED body still both eats and offers picks. Defensible and pre-existing
      (Fusion keeps translucent bodies selectable), but now that the hidden case
      is spelled out at length the omission reads as an oversight; one explicit
      line in the module doc.
      [src: code-reviewer, SEL-6 slice 2026-08-08]

- [ ] (P2, XS) **CI-2 — `deploy-path` never got the per-SHA concurrency fix, so
      it is still evicting runs** (`.github/workflows`). Filed 2026-08-08 by the
      orchestrator from the CI board. `ci.yml` and `e2e.yml` both key their PUSH
      concurrency group on `github.sha`; `deploy-path.yml:39-41` still reads
      `group: deploy-path-${{ github.ref }}` with `cancel-in-progress: false`,
      and its header comment justifies that with "Runs QUEUE instead, so one
      always completes." That reasoning is the exact one CLAUDE.md records as
      false: a group admits one RUNNING plus one PENDING run, and a newer
      arrival evicts the pending one no matter what `cancel-in-progress` says —
      which only governs runs already holding a runner.
      EVIDENCE: `207d36c` (run 31237861400) and `e53e4e4` (run 31237776502) both
      came back `cancelled` on `deploy-path` while their `ci` and `e2e` runs
      completed. `list_workflow_jobs` on 31237861400 returns
      `{"total_count": 0}` — no job ever started, which is the eviction
      signature, not the `timeout-minutes` one (a timeout kills ONE job near its
      ceiling and leaves siblings green).
      FIX: mirror `ci.yml`'s expression — per-SHA group on `push`, per-ref on
      `pull_request` — and correct the stale comment in the same commit so the
      next reader does not re-derive the wrong model. Cheap: deploy-path is the
      86 s job, so per-commit runs cost little.
      ACCEPTANCE: two commits pushed back-to-back each get a completed
      `deploy-path` run; no `cancelled` with zero jobs.
      [src: orchestrator CI read, 2026-08-08]

- [x] (P1, M) **SEL-4 — the armed EDGE and shell/draft picks are still 24 px
      dots; only the FACE pick got its raycast** (`apps/web`). SHIPPED
      2026-08-08 (`757ca9f` `e53e4e4` `8cb7700` `207d36c` + this commit): all
      five converted onto ONE shared implementation (`pickSurface` /
      `facePatch` / `pickStamp` / `edgeBand` + `EdgeBandLayer`), each passing
      `recede`; edges get a 24 px `LineSegments2` corridor with a unit-tested
      occlusion decision; hole placement becomes FREE placement with snap
      (behaviour change, flagged to the founder). Dense-hole fixture
      (`seedDenseHolePlate`, seven Ø6 bores on a Ø40 bolt circle) + gate
      `e2e/pick-affordance.spec.ts`, mutation-verified on all three
      conversions. MEASURED: edges 13 px in every direction -> 40–130 px along
      and ≤13 px across; shell reachability 1.7 % -> 95.6 %. NB the item id is
      AMBIGUOUS — there is a second "SEL-4" (hovered-face normal arrow) further
      down this file, and a duplicate "SEL-5" pair as well; flagged for the
      groomer to renumber. Review follow-up 2026-08-08: a HIDDEN body no longer
      occludes the edge band behind it (the reason you hide one), the mate
      conversion got the census gate it shipped without, and the mate hover has
      one owner instead of N writers on one stamp. SEL-1 A2 made
      the drawn surface the primary hit-test for `FacePickOverlay` and lifted
      reachability 9.9 % -> 84.6 %. `EdgePickOverlay` (fillet, chamfer),
      `ShellFaceOverlay` (shell, draft), `MeasureOverlay`, `InstanceMateOverlay`
      and `HolePointOverlay` were NOT converted: `PickNode` is still their sole
      hit-test, so the founder's "picking is very difficult" is unfixed the
      moment the tool is fillet rather than sketch-on-face. Edges need a
      screen-space tolerance band around the polyline rather than a triangle
      raycast, which is why they were deferred and why this is M not S. Two
      riders, both from the 2026-08-06 review: each overlay passes `recede` to
      `PickNode` as it converts (the prop exists and defaults OFF precisely so
      an unconverted surface keeps its aim affordance at full strength); and
      A2's acceptance names a DENSE-HOLE-PATTERN fixture, which the shipped
      gate does not have — the six-face box cannot show a mis-resolved ordinal
      the way seven overlapping bores can. Acceptance A2:
      `docs/design/pre-selection.md` §6. [src: code review 2026-08-06]

- [ ] (P2, S) **SEL-5 — no gate proves the addressed face's trace respects
      OCCLUSION** (`apps/web`). The 2026-08-06 fix (depth-tested `Line2` +
      faint x-ray pass) is evidenced by founder screenshots
      (`docs/screenshots/sel1-bore-trace-*`) and nothing else, because every
      instrument we own for this is a pixel census and the honest direction
      here is FEWER lit pixels — exactly the "a census can reward the broken
      screen" trap FB-17d records. Wanted: an assertion tied to WHERE the brass
      lands (inside the hole's silhouette vs across the plate) rather than to
      how much of it there is. The bored-plate fixture and the island-finding
      sweep that addresses its bore wall already exist in
      `e2e/face-hover.spec.ts`. [src: code review 2026-08-06]

- [x] (P0, S) **CI-1 — `sketch-visibility` gate red since `6d8a8dd`, which never
      got a CI run.** Found 2026-08-06 by reading the e2e run for a SEL-1 push.
      `6d8a8dd` and `be8a2a5` were pushed together; GitHub builds only a push's
      HEAD commit, so the breaking one was never built and left no row to notice.
      FIXED: the gate's 30 % ink floor was calibrated to a framing FB-22 has
      since improved (the sketch camera now rests over the face centre, which is
      wider — 35.5 -> 26.6 px/mm), and its stated model was backwards. Floor
      restated around what the gate actually discriminates (hundreds vs ZERO)
      and mutation-verified at 0. AMENDED 2026-08-06 (code review): the first
      cut kept BOTH a 12 % ratio and a 120 px floor, and at the shipped framing
      the ratio computes to 128 — so it decided nothing and left the gate
      framing-coupled, which is the very fault it was fixing. One instrument
      now (the absolute count), preceded by a `pxPerMm` band so the next
      re-framing fails at the calibration line with a message. Two wrong
      hypotheses were measured away first (snap-corrupted DRO calibration;
      unsettled camera ease) — both recorded in ROADMAP so nobody re-derives them.

### FOUNDER SESSION FEEDBACK 2026-08-01 — eleven reports from one evening of real use

The founder modelled in the app and reported the following. These outrank the
rest of the queue: they are the daily-driver question answered directly. The
recurring shape is NOT missing capability — it is capability that cannot be
REACHED (a dimension mode nobody added, sketch-on-face buried in a context menu,
free-rect framing built but never triggered, picking that never says what it is
about to hit).

- [x] **FB-1 — the extrude "flipped to xy", and a sketch on a face kept "snapping
      back" so it could not be seen.** ONE bug, FIXED `5bd4c46`. The auto-fit in
      `Viewport.tsx` slammed the camera to `ISO_DIR`/up=+Y on every run, and its
      trigger `fitKey` includes the geometry id, so every extrude re-imposed iso.
      Now re-frames distance/target only; direction/up preserved after the first
      fit. Not yet verified against the Playwright screenshot specs.
- [x] **FB-1b — the other half of FB-1: the sketch you were drawing on the face
      was not merely re-framed, it was NOT BEING DRAWN.** Measured on the real
      stack before the fix: a rectangle scribed on the top face of a 20 mm cube
      put **0** pixels of `sketch.scribe` on the canvas out of ~1 600 px of line,
      and the mm grid appeared over roughly half the face in speckled patches —
      a sketch seated on a face is coplanar with it, so the ink lost the depth
      tie. Which side won was not even stable between runs (opaque-queue material
      ordering), which is why one QA pass saw ink and another saw none. Fixed
      three ways in `SketchScene.tsx`: the ACTIVE sketch's ink draws on top
      (`depthTest:false` + `transparent` + renderOrder — WebGL has no polygon
      offset for lines/points, so a bias was never available for the ink), the
      sheet meshes and the plane grid take a coplanar polygon-offset decal, and
      committed sketches are untouched so they still sit behind the solid. The
      contrast half of the founder's report is a second, independent defect:
      `scribe` measures **16.2:1** on the carbide ground and **1.32:1** on a lit
      aluminium face, so white-on-stock was unreadable even with depth won. No
      flat ink clears 3:1 on both grounds, so the GROUND changes — LAYOUT BLUING,
      a feathered `carbide` wash laid on the picked face (the metaphor the token
      file already claimed), taking the scribe to **5.9:1**. Gated by
      `e2e/sketch-visibility.spec.ts`, which fails on the parent commit.
- [x] (P0, M) **FB-2 — a sketch line will not select at all**, so it cannot be
      dimensioned ("I try to click on a line to [assign] height"). Pick path, not
      discoverability: `applyConstraintAction("distance")` needs exactly one LINE
      and `pick.ts` states "Points win within tolerance because they are the finer
      target" (`PICK_TOLERANCE_PX = 8`) — a click near a line may resolve to an
      endpoint POINT with nothing on screen saying so. Bisect vs `d8a4126`
      (PERF-4b fused per-face primitives + changed draw groups) in flight.
- [x] (P0, M) **FB-3 — picking a FACE is "very difficult"** — finicky rather than
      dead. Wants a measured hit region, small-vs-large faces, zoom and grazing
      angle, not an impression. Likely the same defect as FB-2.
- [x] (P0, M) **FB-4 — a cut extrudes AWAY from the material and removes
      nothing** ("I select a sketch do a cut it somehow misses everything going a
      different way"). `defaultExtrudeForm` (`features/extrude.ts:66`) hardcodes
      `direction: "normal"` and never consults the operation; an on_face datum's
      `z_dir` is the OUTWARD face normal (`kernel/faces.py:13`). Fix: default
      direction from operation + plane kind (cut on a face -> into the material),
      re-default when the operation is switched unless overridden, show it in the
      ghost. The typed `cut_removed_nothing` error made this look like user error
      for months — an error message guarding a bad default.
      DONE 2026-08-03 (frontend-builder): `defaultExtrudeDirection(operation,
      provenance)` + touch-tracked override (`withOperation`/`withProfile`/
      `withDirection`); base planes deliberately left alone. The ghost now
      renders for face-seated sketches (their `on_face` basis was missing from
      the solved-layer walk) and the editor says where the sweep goes. Closed
      form in `e2e/extrude-cut-direction.spec.ts`: 8 000 mm³ → 7 500 mm³.
- [x] (P1, M) **FB-5 — cannot attach a sketch to a face; hovering a face should
      offer it.** The capability exists but only as `ctx-sketch-on-face` in a
      right-click Tools menu, which then enters a face-pick mode (so FB-3 may
      also block it). "New sketch" offers base planes only, so concluding it is
      impossible is the correct reading of the UI.
- [x] (P1, S) **FB-6 — sketch ink is invisible on the face it sits on.**
      `SketchScene.tsx` sets `depthWrite={false}` but leaves depth TESTING on and
      has no `renderOrder`/`polygonOffset`; a sketch on a face is coplanar with it
      by construction, so the ink z-fights away. Also check scribe contrast on a
      bright aluminium face, not just the dark void.
      BOXES TICKED 2026-08-06 while landing FB-7: FB-2/FB-3/FB-5/FB-6 were all
      closed by shipped work and only the checkboxes were stale — FB-2 never
      reproduced (its real causes shipped as FB-12 `b6d2f2d` and FB-14
      `d2e2162`), FB-3/FB-5 by SEL-1 A2 (`8b693f5`, affordance 9.9 % → 84.6 %
      against a 50 % floor), FB-6 three ways in `SketchScene.tsx` by FB-1b
      (`b6d2f2d`). No new work; the record was lying about what was open.
- [x] (P1, L) **FB-7 — editor panels cover the model and cannot be moved**
      (Feature tree > new Datum plane; photographed). `Viewport.tsx:733` already
      measures chrome obstructions into a FREE rect and `framePose` already fills
      it — but `framing()` is only consulted during a fit, and the auto-fit runs
      only on `fitKey`, so opening a panel triggers nothing. Order: dock editors
      into a rail (overlap becomes structurally impossible), THEN trigger the
      free-rect fit for residual floating chrome (safe only since `5bd4c46`),
      THEN compact as a separate density pass. Compaction alone is not the fix —
      a smaller panel still covers the part.
      DONE 2026-08-06 (frontend-builder): editors DOCK. `ChromeRail` is one
      column per side at the seat the tree/inspector already hold, and
      `EditorCard` portals into it — one shell, so all 17 editors moved at once
      and the workspaces with no rail keep floating. Overlap is now structurally
      impossible, not merely smaller, and the charged inset is unchanged, so the
      free rect stays `356,24,888,758` and the camera never moves. The residual
      1.2 % offender was NOT chrome: the extrude ghost drew on the far side of
      the sketch plane because the origin-datum bases were kernel-frame (Z-up)
      while the scene renders Y-up — measured body y∈[0,10] z∈[−15.4,16.6] vs
      ghost y∈[−16.6,15.4] z∈[0,10]. That is FB-9's mechanism too, fixed in
      `sketch/plane.ts` (`sceneOriginBasis`/`resolveDatumSceneBasis`; the kernel
      algebra is untouched so client and server still agree on (u,v)). Two
      latent bugs surfaced with it: two camera rigs deadlocked over one camera
      (fixed — the part rig releases its ease when the sketcher takes over), and
      the ghost needed `depthTest:false` to be visible at all now that it lands
      INSIDE the body. `founder-picking.spec.ts` FB-7 is a plain `test` with no
      `extraSelectors`, mutation-verified red both ways.
- [ ] (P0, L) **FB-8 — "too many [points] to see what you are clicking"; wants
      Fusion/Plasticity pre-selection** — a snapping pointer, the FACE (not the
      body) highlighting under the cursor, and a small axis showing direction.
      `ModelMesh.tsx:37` types highlight as per-BODY (`"none" | "hover" |
      "selected" | "feature"`), so hovering glows the whole solid. This is the
      root of FB-2/FB-3 as EXPERIENCED: a mis-aim is invisible instead of visible
      and free. The hovered-face normal also pre-empts FB-4 — you would see which
      way "out" points before authoring. Spec IN FLIGHT (vision-steward).
- [ ] (P0, S) **FB-9 — "the extruded is not on the same plane"** (photographed,
      base-plane sketch, ADD, NORMAL, 10 mm). Needs numeric settlement: solid min
      extent along the normal vs the plane offset, and footprint coincidence with
      the profile. Note `PartPage.tsx:976` says a sketch on XY+30 renders its ink
      at z=30 — ink placement and the kernel's plane origin are computed in two
      places, which is where they drift. Distinguish wrong GEOMETRY from wrong
      RENDERING; they look identical on screen and have different fixes.
- [x] (P1, M) **FB-10 — drawings cannot dimension edge-to-edge, so a shell wall
      thickness is unmeasurable.** `LinearMeasurement` (`schemas/drawings.py:320`)
      is edge-length OR point-to-point between two ENDPOINTS. Point-to-point
      measures those points, not the perpendicular thickness, and is wrong as soon
      as they are not aligned across the wall. `angular` already takes
      `edge_a`/`edge_b`, so the two-edge pattern exists and the union is designed
      to extend additively. Add `EdgeToEdgeMeasurement` with a typed refusal for
      non-parallel edges rather than a confidently wrong number. Needs a QUIET
      tree: it regenerates contracts + ts-client.
      SHIPPED 2026-08-03 (backend-builder): `EdgeToEdgeMeasurement{edge_a,edge_b}`
      joined `LinearMeasurement` additively; geometry raises
      `DimensionNotParallelError` → typed `dimension_not_parallel`, NO value, for a
      converging/skew/degenerate pair. E2e `drawing-wall-thickness.spec.ts` reads
      5.000 off a real housing wall and proves the refusal.
- [x] (P2, S) **FB-11 — nothing in the app says which BUILD it is.** The founder
      tests from a GitHub Codespace, so a report cannot be tied to a commit and
      "already fixed or still broken" is unanswerable. Inject the git SHA + build
      time via Vite `define`, surface it quietly with a `data-testid`. Small, but
      it removes a whole class of wasted round-trip — two fixes landed mid-session
      and neither side can say whether the last report included them.
      SHIPPED 2026-08-04: `vite.config.ts` injects `__BUILD_SHA__`/`__BUILD_TIME__`
      (`-dirty` suffix when the tree is), read through `src/lib/build.ts`, printed
      in the `?` key card's footer — reachable everywhere, costing the viewport
      nothing. Falls back to `unknown` with no git; 4 tests cover the fallback so
      it can never render `Build undefined`.
- [x] (P0, S) **FB-12 — a click that drifts 5 px is silently discarded, which is
      what "the line wouldn't even select" actually is** (qa-tester, measured
      2026-08-01; `docs/QA-REVIEW.md` "founder session: the picking reports").
      `SketchScene.tsx:353` returns early on r3f `e.delta > CLICK_SLOP_PX` (=4).
      Measured exactly: 0–4 px SELECTS, 5 px DEAD, and dead means nothing at all —
      no hint, no cursor change, no log. Playwright's `mouse.click` moves ZERO
      pixels, so the whole suite proves a path no hand takes; a trackpad drifts
      5–10 px routinely. Fix by intent (did the camera actually orbit / did the
      pointer leave the target) rather than raising one constant, and add a
      real-pointer-drift case to the e2e so the gate stops flattering us.
      Encoded today as a `test.fail()` in `e2e/founder-picking.spec.ts`.
      FIXED — the rule is now `sketch/clickIntent.ts`, shared by both call sites
      (drawing surface + plane choice, which carried the same inline 4 and could
      drift apart). Distance alone was the wrong discriminator, so it is not one
      constant: <=12 px is a click at any speed (Qt 10 / GTK 8 / Windows 4-at-96dpi
      = 8 at 2x / the web gates clicks by ZERO distance — 4 was below every
      convention), 12-24 px is a click only under 0.2 px/ms (a slow wobble is a
      hand, a fast flick is a pan), beyond that it is a drag. `e2e/click-drift.spec.ts`
      drives down/move/up so it exercises real travel; mutation-verified by
      restoring 4, which turns it red while the drag-rejection case stays green.
- [x] (P1, S) **FB-13 — Escape with nothing selected ENDS the sketch**, so the
      reflex after a click that appeared to do nothing throws you out of the
      sketcher (qa-tester, 2026-08-01). `escapeAction` (`sketch/tools.ts:402`)
      falls through to `"exit"` for tool `select` + empty selection and
      `PartPage.tsx:1029` routes that to `finishSketch()`. The strip's own
      caption advertises Esc as SAVE, so one key has two advertised meanings in
      one state. Compounds FB-12/FB-2: the recovery gesture costs you the sketch.
      Encoded as a `test.fail()` in `e2e/founder-picking.spec.ts`.
      FIXED — the cascade unwinds (editor -> placement -> tool -> selection) and
      then STOPS: `escapeAction` answers `"none"` at rest, and the store raises a
      hint naming the chip that does finish rather than doing nothing silently.
      It still answers `"exit"` when the sketch holds no work (the plane-pick
      step, or an empty buffer), so backing out of a sketch opened by mistake
      stays keyboard-first. The latent twin went with it: `escape` weighed only
      `selection`, so a picked constraint GLYPH fell through the same rung and
      wiped the session. CALLER WORK LEFT, outside this territory —
      `SketchStrip.tsx` still puts `shortcut="Esc"` on the Save chip (caption and
      binding must agree), `PartPage.tsx`'s `if (action === "exit")
      finishSketch()` is now dead for a drawn sketch, and `founder-picking.spec
      .ts`'s FB-13 `test.fail()` now fails for a NEW reason (no feature is minted
      at all).
- [x] (P2, S) **FB-14 — a plain click ACCUMULATES picks instead of replacing
      them** (`pick.ts:168` `toggleSelection`), so clicking line A then line B
      selects both and `distance` refuses with "Select one line to dimension."
      Every other CAD replaces on a plain click and adds on Ctrl/Shift. A user
      hunting for a click that works builds a selection that cannot be
      dimensioned. Found while measuring FB-2.
      FIXED — `applyPick` (`sketch/pick.ts`): a plain click REPLACES (stacked
      candidates still cycle, one pick at a time), Shift or Ctrl/Cmd ADDS, and a
      modifier-click that MISSES keeps the selection being assembled. The store
      reads the modifier state the aim already tracks (Shift = `axisLock`,
      Ctrl/Cmd = `snapSuppressed`), so no scene change was needed; `selectAt`
      also takes an explicit mode for a caller holding the click event. The
      `aria-pressed` fit-point handles stay toggles — the modifier-free
      multi-select path. Every multi-entity constraint spec now Shift-clicks.
- [x] (P1, M) **FB-15 — every draw tool is click-then-click; users expect
      click-and-DRAG.** `tools.ts` `case "rect"` takes a corner click then a
      second point click (same shape for line/circle/arc). Press-drag-release is
      the near-universal convention for a rectangle in every tool the founder
      compares us to, and the two-click form should remain as the fallback (it is
      better for precision and for touch), not be replaced. NOTE this composes
      with FB-12: the click/drag discriminator being built for the 4 px slop is
      exactly the machinery a drag-to-draw tool needs — do these together or the
      second will fight the first. Acceptance: press-drag-release draws the
      rectangle, a click-click still works, and a drag that turns out to be an
      orbit still orbits. [src: founder 2026-08-01]
      SHIPPED 2026-08-03 with FB-16 (one interaction). The PRESS places the first
      point, so the rubber band, snap and Escape all run through the one `pending`
      sequence two clicks already used; the release completes the shape only when
      `isClick` (FB-12's discriminator, no second threshold) says the pointer
      travelled. Two-point tools only (`dragDraws`), mouse/pen only — on touch a
      two-finger pan delivers a primary pointer-down, so tap-then-tap stays.
- [x] (P1, L) **FB-16 — dimensions should be typed AS YOU DRAW, in inline text
      boxes, not applied afterwards.** "usually dimensions are applied
      automatically with text boxes." This is how Fusion / SolidWorks / Onshape
      sketching actually works: draw a rectangle and width/height fields appear at
      the cursor, Tab moves between them, typing a value DRIVES that dimension and
      Enter commits — you rarely go back and dimension afterwards. It closes the
      loop on the founder's very FIRST report ("dimensions are not working when I
      click a line to [assign] height"): the reason that path felt broken is that
      it is the wrong path — the dimension is supposed to be offered at creation.
      We already have the pieces: `dimensionExpr.ts` parses driving expressions,
      `applyConstraintAction("distance")` returns an editor request rather than a
      constraint, and `dimension-input` exists. What is missing is the
      at-the-cursor input during the draw gesture and the Tab order between
      fields. Design it against `docs/design/pre-selection.md`'s vocabulary so the
      snap glyph and the dimension field do not fight for the same pixels.
      [src: founder 2026-08-01]
      SHIPPED 2026-08-03 with FB-15. A drafting tag hangs off the shape's far
      corner (clear of the snap mark's own pixels): live readout while dragging,
      typeable cells on release. Typing rewrites the geometry AND records a
      driving dimension; a dimensioned rectangle also gets the rigidity set that
      keeps it rectangular. Cells are UNCONTROLLED on purpose — a controlled one
      loses the first digit of "50" to its own re-render (measured).
- [x] (P0, M) **FB-17 — the browser suite cannot catch the class of bug the
      founder found, and that is fixable.** Every FB-* defect this evening lived
      in the gap between Playwright's API and a hand/eye. Four gaps, each with a
      concrete gate: (a) INPUT FIDELITY — `mouse.click()` moves 0 px and takes
      0 ms; a trackpad drifts 5-10 px and dwells 40-120 ms, which is the entire
      reason FB-12 survived. Add a `handClick(page, x, y, {drift, dwell})` helper
      that moves, jitters, dwells and releases, sweep drift 0/2/4/6/10 in a spec,
      and PREFER it over `mouse.click` for interaction tests. (b) REACHABILITY —
      specs click `getByTestId(...)` on the DOM pick button, so they hit a 24 px
      dot perfectly and never learn the face is dead; test IDs are right for
      asserting STATE and wrong for asserting reachability, so pick tests must
      click a COORDINATE over the rendered entity. (c) MEASURE the affordance:
      assert a clickable FRACTION of a face's screen area (the QA pass measured
      2.2 %), not a boolean "the pick worked", which passes on a dot.
      (d) PERCEPTIBILITY — `countSketchInkPixels` returned 926 729 on the broken
      screen vs 1 881 on the working one, i.e. it rewards the failure; assert
      CONTRAST between ink and the surface behind it plus the presence of context
      in frame. Plus: assert INVARIANTS across actions (record camera direction,
      extrude, assert unchanged — one line, would have caught FB-1) and
      occlusion (model screen bbox must not intersect panel rects — FB-7).
      Acceptance: the helper exists, `founder-picking.spec.ts`'s `test.fail()`
      cases flip to real assertions as each fix lands, and every new gate is
      mutation-verified. [src: founder "How do you catch this stuff with
      playwright?" 2026-08-01]
      DONE 2026-08-02 (qa-tester): `e2e/{hand,reachability,perception,
      invariants}.ts` + `qa-harness.spec.ts` (17 calibration/negative-control
      specs). Measured: drift sweep 0/2/4/6/10 all select; pick affordance
      45/454 = 9.9 % (floor 50 %, `test.fail` until FB-3/FB-5); rebuild moves
      the camera 0.071 deg; the extrude editor covers 9.0 % of the body and
      declares no `data-viewport-chrome`, so the app's own fit is blind to it.
- [ ] (P1, L) **FB-18 — a 50x mirror/rotate never finished; it "errored and
      stopped".** Founder, 2026-08-01. Almost certainly the gateway's typed
      `upstream_timeout` (`py_kit/errors.py:134`) — which says the honest thing
      ("we gave up waiting") and is useless to the user, because the work may
      have been progressing fine. TWO questions, and they have different fixes,
      so MEASURE before building: (a) is a 50-instance pattern inherently that
      expensive (rebuild scales ~N^1.85 per docs/PERF.md, so it may legitimately
      be), or is the pattern RE-EVALUATING its source body per instance? If the
      latter the fix is caching and no queue is needed. (b) If it is genuinely
      long, a long compute must stop riding an HTTP request: move evaluation onto
      the arq/redis queue already on the roadmap so it becomes a JOB — submitted,
      progress-reported, cancellable, resumable — i.e. "47 of 50, 12 s left,
      cancel?" instead of a dead request. Note K8s does NOT solve this and adding
      it would not have helped: an HPA adds replicas for THROUGHPUT and cannot
      speed up one in-flight request, CPU limits throttle rather than scale, and
      vertical scaling is capped because OCP does not release the GIL (measured:
      one geometry worker uses ~1.1 cores whatever the box has, docs/PERF.md
      §CONCURRENCY). Acceptance: the 50x case named as a benchmark with its
      measured cost and where the time goes, then the fix that measurement
      implies. [src: founder 2026-08-01]
- [ ] (P1, M) **FB-19 — the chrome is too sparse; compact it.** Founder,
      2026-08-01, and distinct from FB-7: FB-7 stops panels COVERING the model,
      this makes them worth the pixels they take. Note UI-W4 already did one pass
      ("feature editors stop being 12-row web forms") and the founder still says
      it is not dense enough — so treat the previous pass as insufficient rather
      than done. Evidence is the founder's own photo: `EDIT EXTRUDE` spends six
      full-width rows on Profile / Distance / Operation / Direction / Merge /
      actions, every label stacked ABOVE its control, plus a permanently-visible
      helper sentence ("Fuse into the touching body."); the left panel spends six
      rows listing XY/XZ/YZ + X/Y/Z axis. Concrete levers, in order of return:
      label BESIDE control instead of above (halves row height on a form that is
      almost all short values); the two 2-state toggles (Operation, Direction)
      onto one row as segmented controls; helper prose behind an info affordance
      rather than permanently resident; the origin list as a 3x2 grid, not six
      rows. THE FLOOR, which is not negotiable and must be stated in the commit:
      WCAG 2.5.8 24px minimum target size (`PickNode` already cites it), visible
      focus, AA contrast, and the touch specs still green — a panel compacted
      into unusability on a laptop trackpad is a worse defect than a tall one.
      Judge it the way the design mandate says: screenshots side by side against
      a Fusion/Plasticity reference at 1600 AND 1280, and measure the viewport
      pixels reclaimed rather than asserting it feels tighter. [src: founder
      2026-08-01]
- [ ] (P0, L) **FB-20 — the FLOW from sketch to feature, and the parts page,
      both need an overhaul.** Founder: "we need to fine tune the flow from
      drawing the sketch. Also, the main pages for selecting parts... Flow is
      critical for users. Think about it as you build. How should we direct the
      user? Hopefully in a way to leave fusion and go OS." Now a standing rule in
      CLAUDE.md's design mandate, so this item is the first concrete cash-out,
      not the whole of it. TWO surfaces. (a) SKETCH -> FEATURE: today you draw,
      then hunt. The solved sketch should OFFER its likely next action with the
      profile already selected; extrude wants a draggable arrow in the viewport
      with the numeric field as the precision fallback (we have the form and no
      handle, which is the biggest "not a modeling tool" gap we have); dimensions
      typed during the draw (FB-16); and no ambiguous exit (FB-13). (b) PARTS
      PAGE: benchmark Onshape's document list, NOT Fusion's data panel which is
      genuinely weak — recent-first, searchable, thumbnails that show STATE
      (solved / errored / stale), folders that do not read as a filesystem (WS2
      folders already shipped, so this is presentation over an existing model).
      Acceptance: a named flow walked end to end with the CLICK and KEYSTROKE
      count before and after, at 1600 and 1280, against a Fusion/Onshape
      reference — a flow claim with no count is an opinion. Deliberately P0/L:
      every FB-1..FB-19 report was a flow failure rather than a missing
      capability, so this is the root the others are symptoms of. [src: founder
      2026-08-01]
- [ ] (P0, M) **FB-21 — the origin axis glyphs are labelled in KERNEL space but
      drawn in SCENE space, which the GLB rotation has already turned.** Founder,
      2026-08-02: *"check the axis. Turn on the axis and compare them to the view
      cube."* MEASURED, not inferred. A 40x20 rectangle on Plane.XY extruded
      10 mm gives GLB mesh-local extents X 0.04 / Y 0.02 / **Z 0.01** — the
      extrude is along kernel +Z, correct — and the glTF node carries rotation
      `[-0.7071, 0, 0, 0.7071]`, a -90 deg turn about X, so **kernel +Z maps to
      scene +Y** (and kernel +Y to scene -Z). `glbGeometry.ts` states it bakes
      that node matrix into the merged buffer, and no compensating rotation
      exists on the model mesh or the origin group (checked). But
      `OriginGeometry.AXIS_DIRECTION` draws X/Y/Z at scene
      `[1,0,0]/[0,1,0]/[0,0,1]` — an identity. So the glyph labelled **Z** points
      along scene +Z, which is where the kernel's **-Y** lives, while the part's
      height runs along scene +Y where the glyph labelled **Y** is drawn. Y and Z
      read as swapped against the model. `Viewport.tsx` compounds it: camera
      `up` is `(0,1,0)` and `upFor()` detects top/bottom with
      `Math.abs(dir.y) > 0.99` — Y-up — so the ViewCube's TOP looks down the
      part's true height while the axis captioned Z points sideways. That is the
      disagreement the founder asked us to check.
      **NOT yet established, and the next step:** whether `sketch/plane.ts`'s
      bases (XY normal `[0,0,1]`, stated as build123d's kernel triples) are
      likewise un-rotated — if so the PLANE glyphs mislead the same way, and the
      plane a user picks is not the plane they see. Settle it by rendering, not
      by reading: turn the axes on, screenshot against the ViewCube at a named
      view, and compare with a body of known dimensions. Do NOT "fix" the labels
      before that — geometry is verified exact (FB-9), so this is a naming/render
      frame bug and swapping constants blind could break the half that is right.
      Acceptance: one stated frame convention, documented; axis glyph, plane
      glyph, ViewCube and model agree; a gate asserting the labelled Z glyph is
      parallel to the extrude direction of an XY sketch. [src: founder 2026-08-02]

- [x] (P0, M) **FB-22 — the sheet now says where zero is, and you can start
      there** (founder 2026-08-02: *"there isn't an origin to start a drawing
      from."*). `sketch/snap.ts` offered four kinds, every one derived from
      geometry already drawn, so the FIRST point of a sketch could hold onto
      nothing but the grid — and nothing on screen marked (0,0). Shipped: the
      plane's own frame, drawn (`sketch/origin.ts` + `SketchOrigin` — a
      centre-punch ring at zero with both axes, solid on the positive half and
      phantom on the negative, letter engraved on the positive half; the
      OriginGeometry dialect, in plane (u,v) so it survives a world-frame
      change) and SNAPPABLE (`origin` / `x-axis` / `y-axis` kinds, ranked with
      endpoints and yielding to a corner drawn at zero, the axes last of all).
      Named honestly per plane kind: a datum's zero is "Origin", a face-seated
      sketch's is "Face centre" with the caveat that it MOVES — the QA3-2
      mechanism, now stated where the user reads it. Gates:
      `e2e/sketch-origin.spec.ts` draws a rectangle from a 6 px-off aim with the
      grid OFF and asserts the persisted corner is exactly (0,0). [src: founder
      2026-08-02]
- [x] (P0, M) **FB-23 — undo and redo, in the sketcher, on the SKETCH's own
      stack** (founder 2026-08-02: *"there are no undo or redo buttons."*).
      `HistoryGroup` was rendered by the part and assembly bands and not by
      `SketchStrip`, so entering the sketcher removed undo exactly where the
      work is most reversible. The trap was wiring the familiar chrome to the
      familiar handler: part history undoes FEATURES, and a sketch in progress
      is not yet a feature. So the store grew its own `past`/`future`, RECORDED
      BY DERIVATION — the `set` wrapper snapshots any transition that bumps
      `revision`, which is already the definition of a persisted sketch edit, so
      a new action is undoable by construction. Undo bumps `revision` too, so a
      restored sketch saves and re-solves. Same shared `HistoryGroup`, same
      Ctrl+Z grammar, plus a `scope` caption naming what one step reverses.
      Gate: `e2e/sketch-origin.spec.ts` asserts the feature tree and the 8,000
      mm³ body are UNTOUCHED across sketch undo/redo. [src: founder 2026-08-02]
- [ ] (P2, S) **A bound sketch undone to ZERO entities cannot persist that
      state** (`apps/web`). `PartPage.persistBuffer` early-returns when
      `entities.length === 0`, which predates sketch undo (nothing could shrink
      the buffer before FB-23), so undoing the last entity of a SAVED sketch
      shows an empty sheet while the server keeps the last geometry — and
      Finish then closes without reconciling them. Fix in the sync loop, not the
      store: an empty bound sketch is a legal state to save. [src: FB-23
      as-built]
- [ ] (P3, XS) **Fold the two private `calibratePlane` copies into
      `e2e/planeMap.ts`** (`apps/web`). `constraints.spec.ts` and
      `sketch-snap.spec.ts` each carry their own copy of the plane→screen
      calibration; the shared module landed with FB-22 rather than adding a
      third. Next time either spec is opened, import it. [src: FB-22 as-built]

**QA verdicts on the founder block (qa-tester, 2026-08-01, HEAD + bisect):**
`d8a4126` (PERF-4b) is **EXONERATED — do not revert**: face picking uses drei
`Html` DOM buttons, `ModelMesh` has no click handler at any of `3cf6650` /
`d8a4126` / `3f4fbe6`, and every pick probe is identical to the character at all
three. **FB-2 does not reproduce as stated** (a clean click selects the line and
`D` dimensions it, everywhere) — FB-12/FB-13 are the real defects behind it.
**FB-3/FB-5 reproduce**: 32 of 1457 sample points (**2.2 %**) over the body are
live face targets; the other 97.8 % is dead, and the markers for hidden faces
draw over the visible ones. **FB-6's z-fighting diagnosis is REFUTED** — the ink
renders fine; the plane card fills the frame as a featureless grey slab with no
grid, no body, no scale, and `countSketchInkPixels` goes UP 500× when the sketch
becomes unusable, so a gate built on it would pass. **FB-9 is not wrong
geometry**: solid min along the normal equals the plane offset to 0 on XY, XZ,
YZ and XY+30, volume exactly 10000.000000 mm³, footprint exactly the profile —
so it is the pre-`5bd4c46` camera snap or a stale Codespace bundle (see FB-11).


- [ ] (P1, L) **QA3-2 — a sketch on an imported face has NO reference to the
      import, and its origin is the face's area centroid** (frontend + geometry).
      Two things compound: `faces._face_plane` puts the datum origin at the face's
      AREA centroid (not the part origin, not any feature of the part), and
      `sketch/snap.ts` snaps only to the sketch's own entities and the grid —
      never a body edge, a hole centre, or projected geometry — with no way to
      dimension to imported geometry. Measured consequence: a register ring drawn
      at sketch (0,0) on a vendor plate's back face came out **0.065111070 mm**
      eccentric to the shaft bore, exactly the centroid shift a previously-added
      Ø3 hole caused (`15.5·π·1.5²/(1739.29−15.76π−π·1.5²)`, agreeing to 9
      decimals) — a scrap part with every number on screen correct. Acceptance:
      projected/reference geometry from the body into the sketch (at minimum
      circular-edge centres + straight edges of the sketched face), snappable and
      dimensionable; and the sketch frame's origin drawn and named against the
      part. [docs/QA-REVIEW.md 2026-08-01 QA3-2]
      PARTIAL 2026-08-02 (FB-22): the origin half is DONE — the sketch frame's
      zero is drawn, snappable, and named per plane kind, so a face-seated
      sketch's origin now says "Face centre" and that it moves. What remains is
      the projection half: body edges/hole centres projected into the sketch,
      snappable and dimensionable.

- [ ] (P1, M) **SEL-1 — default hover lights the whole body; a working
      engineer needs the FACE** (`apps/web`). `ModelMesh.tsx`'s pointer handler
      already resolves the exact face ordinal under the cursor
      (`faceOrdinalOf`) and throws it away; extend to `onPointerMove`, route
      the hovered ordinal through the SAME localized-highlight machinery
      "feature selected" already uses (`setFaceMaterials` + `subsetEdges`), and
      reuse existing `viewport.facePick.hover`/`viewport.hover` tokens — zero
      new palette. Graceful fallback to today's whole-body glow when the mesh
      can't be face-partitioned. Also fixes armed face/edge picks (datum,
      hole, shell, draft, sketch-on-face, fillet, chamfer): the raycast
      becomes the PRIMARY hit-test (click anywhere on the face/edge), demoting
      `PickNode`'s fixed 24px centroid/midpoint button to a keyboard/touch
      fallback. Design + acceptance A1/A2/A7: `docs/design/pre-selection.md`
      §1, §6. [src: founder]
      **A1 SHIPPED 2026-08-05 — the pointer now addresses a FACE.** Hover
      resolves the ordinal under the cursor and routes it to its own draw group
      (`setFaceMaterials` slot 4) with its boundary traced by `subsetEdges`;
      the whole-body glow survives as the fallback for a mesh that cannot be
      face-partitioned, or a single-face body. Gated by `e2e/face-hover.spec
      .ts` (5 specs), mutation-verified: deleting `onPointerMove` turns "the
      addressed face FOLLOWS the cursor" red (distinct ordinals seen across a
      grid sweep 2+ -> 1) while the arrival case stays green — r3f re-fires
      `onPointerOver` only on mesh ENTRY, never between faces of one fused
      mesh, which is the whole defect. Two deviations from the spec, both
      forced by the founder capture rather than by taste: the surface tint is a
      NEW token (`facePick.hoverTint` #EFD6AE) because the reused
      `hoverSurfaceTint` is ~5 % off white — invisible once localized to one
      face, i.e. a cue that does not cue; and the traced boundary draws
      `depthTest:false`, because its segments are numerically identical to the
      body-wide edge overlay's and the two came out STIPPLED. A2 (raycast as
      the primary hit-test for armed picks — the 9.9 %-vs-50 % reachability
      floor) and A7 remain OPEN; this ships the hover cue, not the hit-test.
      **A2 SHIPPED 2026-08-05 — the drawn face IS the target: 9.9 % -> 84.6 %.**
      `ModelMesh` publishes its geometry through `partView`; `FacePickOverlay`
      raycasts it and resolves the struck triangle to a B-rep ordinal, which is
      already `OverlayFace.index`, so there is no mapping table to drift. All
      three armed-pick call sites (sketch-on-face, datum, hole) get it for free.
      `PickNode` is unchanged and demoted to what §5 asks: keyboard focus,
      screen-reader name, touch target. A hit on a NON-pickable (non-planar)
      face is ignored rather than snapped to a neighbour. Both FB-3/FB-5
      `test.fail`s in `founder-picking.spec.ts` flipped to real assertions —
      and BOTH needed their measurement repaired first, which is the reusable
      lesson: the affordance case hit-tested the DOM, and `elementFromPoint`
      answers "the canvas" for a raycast handler, so it would have stayed at
      9.9 % with the defect fully fixed; the seat case clicked a hardcoded
      coordinate that is 40 px OFF the body, so it had never once failed for
      the reason it claimed.
      **A7 SHIPPED 2026-08-05 — the reticles stop out-shouting the model.**
      `PickNode`'s mark rests dimmed and returns to full on hover,
      focus-visible and selected; the 24 px hit area (WCAG 2.5.8) is untouched,
      because trading "too many to see" for "cannot hit it" would be the worse
      defect. It follows A2: once the drawn surface is the primary hit-test,
      these marks are the keyboard/touch fallback rather than how you aim. NOTE
      the acceptance asked for a pixel census and it is not deliverable — every
      census in `e2e/support.ts` reads the WebGL canvas, and a `PickNode` is a
      drei `Html` DOM node that puts ZERO pixels on it. That blindness is
      itself the finding: it is why the "DOM-square blanket" survived every
      pixel gate we own. Gated instead on the property that decides it
      (`PickNode.test.tsx`), which is exact and cannot be satisfied by
      degrading anything else. Shots at 1600 AND 1280 under
      `docs/screenshots/sel1-pick-reticles-*`.
      **STATUS 2026-08-06 (code review) — A1 / A2(face) / A7 shipped; the item
      is NOT complete.** An earlier note here said it was, which the unticked
      box already contradicted. What remains, and is now SEL-4: the armed
      EDGE and shell/draft picks (fillet, chamfer, shell, draft) still hang
      their only hit-test on a 24 px `PickNode`, so the reachability floor A2
      measured for faces is untouched on them; and A2's stated acceptance names
      a dense-hole-pattern fixture, where the shipped gate uses a six-face box.
      Two review findings fixed in the same pass: A7's recession was GLOBAL, so
      it dimmed the aim affordance on the five overlays A2 never converted (it
      is now opt-in per surface, and 50 % was under the WCAG 1.4.11 non-text
      floor at 2.98:1 — 60 % measures 3.86:1); and the addressed face's traced
      boundary drew with no depth test, so a bore's far circle painted a bright
      ellipse across the outside of the plate.

- [ ] (P1, S) **SEL-2 — a sketch pick never names what it's about to select**
      (`apps/web`). `sketch/pick.ts` resolves a winning candidate silently;
      extend the existing UI-W5 `SnapMarker` (glyph + word, already shipped
      for drawing) to also render for `hoverPick` in select mode, with one new
      "on-curve" glyph for the entity case (point cases reuse the endpoint/
      centre glyphs already in `SNAP_MARKS`). No change to `toggleSelection`'s
      click-cycle. Design + acceptance A3: `docs/design/pre-selection.md` §2,
      §6. [src: founder]

- [ ] (P2, S) **SEL-3 — stacked-candidate count badge** (`apps/web`). When
      `pickCandidates(...).length > 1` (sketch) or a raycast hit disagrees
      with a nearby armed-pick `PickNode` within tolerance, show a small `+N`
      badge beside the SEL-2 marker (reuses the app's one round-badge
      convention — no new tokens) so cycling is discoverable, not silent.
      Design + acceptance A4: `docs/design/pre-selection.md` §3, §6.
      [src: founder]

- [ ] (P1, M) **SEL-4 — hovered-face normal arrow, doubling as the extrude/cut
      direction control** (`apps/web`, `packages/design`). A single brass
      arrow along the addressed face's normal (planar: `signature.normal`,
      already computed; curved: the raycast-hit triangle normal) on hover;
      while Extrude/Cut is armed it becomes a forward/reverse PAIR wired to
      the editor's existing `direction` field, so the viewport — not a text
      toggle nobody checks while aiming — shows which side removes material.
      World-space length clamped to the face's own footprint (mirrors
      `FacePatch`'s disc-radius formula). New token group `viewport.faceNormal`
      — see `docs/design/pre-selection.md` §4 for the exact fields. Direct fix
      for "a cut misses everything going a different way." Acceptance
      A5/A6. [src: founder]

- [ ] (P2, S) **SEL-5 — the PickNode "DOM-square blanket" is a measured,
      still-open defect** (`packages/design`). `docs/UI-REVIEW.md`'s
      2026-07-24 P2 is unfixed: every armed-pick target paints a visible
      reticle AT REST, always (~22 squares/diamonds on a six-face plate the
      moment Measure arms). Reduce `PickNode`'s rest-state opacity so the
      topology highlight (not the DOM grid) carries the "what's under the
      cursor" read; hover/focus/selected states unchanged. Cheap, isolated,
      independent of SEL-1's larger raycast plumbing — can ship first.
      Acceptance A7: `docs/design/pre-selection.md` §6. [src: founder]

- [ ] (P2, M) **SEL-5b — touch two-phase preview/confirm for ambiguous picks**
      (`apps/web`). Unambiguous tap commits immediately; a tap with >1
      candidate within touch tolerance previews (SEL-2/SEL-3's marker+badge)
      and needs a second tap (or a badge tap) to commit — Loft's own
      considered default, not a verified competitor pattern (neither Fusion's
      nor Plasticity's touch pre-selection behaviour could be confirmed from
      public docs this pass). Acceptance A8: `docs/design/pre-selection.md`
      §5, §6. [src: founder]

- [ ] (P3, M) **SEL-6 — the sketch select tool has no keyboard path at all**
      (`apps/web`). `sketch/pick.ts` resolves purely from pointer coordinates;
      a keyboard user cannot Tab to an existing sketch entity or point.
      Real fix mirrors the lift `FacePickOverlay`/`EdgePickOverlay` already
      paid: give sketch entities/points focusable `PickNode`-style targets.
      Named honestly as an open a11y gap, not implied-closed by SEL-2/SEL-3
      (those extend the *visual* marker; this is the missing input path).
      `docs/design/pre-selection.md` §5, §7. [src: founder]

- [x] (P1, M) **CONC-1 — a modeler's next click lands on a random worker, and
      that throws away most of what scaling out buys** (platform + backend).
      Measured 2026-08-01 (`docs/PERF.md` §CONCURRENCY): 4 users on 4 geometry
      workers pay **2 559 ms** per edit with per-user affinity and **4 753 ms**
      with the random dispatch the stack actually gives (compose DNS
      round-robin / a shared listening socket). Speedup vs. one worker: 3.75x
      sticky, 2.06x balanced-but-affinity-free, **1.21x random.** The rebuild
      cache hit rate is 0.40 with affinity and **0.075** without, at four
      workers — a clean 1/N dilution. Fix: route geometry by a consistent hash
      of `part_id` (the gateway already knows it on every compute route; for
      `/overlay`/`/measure` the tree carries it), or document a
      consistent-hash proxy in front of the replicas. Costs no CPU and is worth
      1.8x on top of any fan-out. [docs/PERF.md 2026-08-01]
      **SHIPPED 2026-08-01** (`gateway/affinity.py`): `GEOMETRY_URL` takes a
      comma-separated list; rendezvous hash on the verified principal (not part
      id — a modeler holds TWO lineages, and every route carries the principal
      while only some carry a part id). Re-measured on the same fleet with the
      queue active: **wall 30.6 s sticky vs 64.9 s random, hit 0.40 vs 0.10,
      `/measure` p50 81 ms vs 3 284 ms**; 8/8 modelers pinned to one worker
      through the real gateway. Degradation: dead worker -> 10 s cooldown +
      retry on the next-preferred (cold, never stranded); set change -> only
      1/N move; saturated worker -> deliberately NOT re-routed.
      `docker-compose.scale.yml` ships the four-replica topology.

- [x] (P1, M) **CONC-2 — overload deletes the service instead of degrading it:
      no admission control anywhere** (platform + backend). 16 simultaneous
      50-feature evaluates at one worker all finished within 0.4 s of each other
      at ~40 s (processor sharing, not queueing). Against the gateway's 30 s
      read timeout that delivers **1 of 16** requests where a plain FIFO queue
      on identical hardware delivers **11 of 16** — same CPU, 11x the useful
      output. Nothing bounds concurrent geometry work: httpx defaults to 100
      connections, anyio's threadpool to 40 workers, and a geometry worker has
      **one** effective core (CONC-5). Fix: a bounded semaphore + queue in front
      of the OCCT routes, returning 503 + `Retry-After` past the bound rather
      than admitting work that cannot finish. [docs/PERF.md 2026-08-01]
      **SHIPPED 2026-08-01** (`py_kit.admission`, on 21 of 24 geometry routes —
      `/meshes/{id}` and the two `/warm` routes are exempt, and the exemption
      list is asserted by a test so a 22nd route cannot silently skip it).
      Re-measured A/B, 16 simultaneous cold 50-feature evaluates, same worker,
      minutes apart: **0 of 16 delivered inside 30 s -> 11 of 16** (8 of 16 at
      the shipped depth-8 default, with the other 8 honestly shed).
      `Retry-After` comes from the gate's own EWMA of service time; three
      distinguishable refusal reasons; nothing is refused after work started.

- [x] (P1, S) **CONC-3 — the gateway calls a healthy geometry service
      "unreachable" after 30 s, on a part size we ship** (backend). Measured
      with ONE user on an IDLE machine: a 200-feature `/overlay` costs 40.3 s
      direct and returns **502 `upstream_unavailable` — "Geometry service is
      unreachable"** through the gateway at exactly `GEOMETRY_TIMEOUT_S = 30.0`
      (`services/gateway/src/gateway/geometry.py:65`). The work completes and is
      discarded; the message blames the wrong component; the same click had to
      be issued **three times** (two 502s, then 22.7 s once the abandoned
      rebuild's checkpoint reached the cache). At 8 users the same thing happens
      on a **50-feature** part (pick p95 30.0 s). Fix has three parts: raise or
      make the ceiling proportional to tree size, distinguish "upstream timed
      out" from "upstream unreachable" in the envelope, and stop paying for
      abandoned work (cancel upstream on client disconnect).
      [docs/PERF.md 2026-08-01]
      **SHIPPED 2026-08-01**: 504 `upstream_timeout` (not 502), with a message
      that says the work is still running and its progress cached; budget 90 s
      by default (40.3 s worst measured cold op + the 20 s queue ceiling +
      headroom), env-tunable via `GEOMETRY_TIMEOUT_S`. The third part was
      resolved the OTHER way on purpose — **do not cancel**: the abandoned
      rebuild's checkpoint reaches the rebuild cache, which is why the measured
      retry was 22.7 s against 40.3 s cold, so cancelling would discard CPU
      already spent. What IS dropped is work that never started — a request
      whose client left before its turn is discarded at the front of the queue
      (`loft_admission_abandoned_total`).

- [x] (P2, S) **CONC-4 — `REBUILD_CACHE_CAPACITY = 8` is exactly four
      modelers, and the fifth costs everyone 79x** (kernel). A working modeler
      holds TWO lineages (evaluate + the `record_history` one a face pick uses),
      so 8 entries is 4 users. Measured hit rate 0.40 (1-4 users) → 0.28 (5) →
      0.15 (6) → 0.125 (8), and `/measure` — the operation PERF-1 made nearly
      free — goes from **244 ms to 19 189 ms**. Related: PERF-1b's prefetch
      takes a slot too, so on a full LRU every warm evicts a live user's
      checkpoint (measured: evictions 24 → 35, hit 0.40 → 0.31), which is
      precisely what `rebuild_cache.py`'s own docstring says must never happen.
      Fix: size the LRU from concurrency (per-worker users x 2 lineages, or make
      it configurable and default higher), and keep warm entries in a separate
      reservation so speculation cannot evict live work. [docs/PERF.md 2026-08-01]
      **SHIPPED 2026-08-01** (kernel): capacity **32**, derived — 8 modelers
      (docs/OPERATIONS.md §6) x 2 lineages = 16 live checkpoints one worker must
      hold without affinity, plus headroom, rounded to a power of two. Priced:
      ~2 MiB/entry at 219 faces and ~4 MiB at 442, so a completely full cache is
      64-128 MiB of the ~1 GiB per-worker budget. Speculation now has a strictly
      weaker claim than live work: a warm's checkpoint is stored SPECULATIVE, is
      always the first eviction victim, and a speculative store that would evict
      a live checkpoint is refused outright. [docs/PERF.md 2026-08-01b]

- [ ] (P3, L) **CONC-5 — OCP does not release the GIL, so one geometry worker
      can never use more than one core** (kernel, likely upstream). Measured at
      **1.05-1.15 cores** with 1/2/4/8 concurrent requests in flight and 11-18
      OS threads live; throughput is flat and latency linear in user count. Every
      other item above is a workaround for this. A `py::gil_scoped_release`
      around the long OCCT calls in OCP would make one worker use one machine;
      short of that, the per-core-worker rule in `docs/OPERATIONS.md` §6 stands.
      Filed at P3 because it is upstream work with a shipped workaround, not
      because it is small. [docs/PERF.md 2026-08-01]

- [x] (P2, M) **CONC-6 — the prefetch is a pessimisation when it does not get
      its head start, and the head start scales with load** (kernel + web).
      Measured on the 50-feature tray, one user, idle: no warm 2 589 ms; warm
      committed immediately **4 742 ms (1.8x WORSE)**; warm + 1 s 3 259 ms; warm
      + 2 s **312 ms (8.3x better)**. The threshold is the rebuild time itself,
      because speculation and the real request race for the single core. So the
      required dwell is ~2.3 s at N=50 idle, ~26 s at N=200 idle, and ~4x that
      again under 4-user load — exactly the sizes where the prefetch is pitched.
      Fix: have the warm yield to a real request for the same lineage (or refuse
      to start when one is in flight) so the worst case is "no benefit" rather
      than "1.8x slower". Complements PERF-1c, which asks the dwell question for
      one user; this one is the multi-user half. [docs/PERF.md 2026-08-01]
      **SHIPPED 2026-08-01** (kernel): a warm yields the CORE, not just the
      slot. `evaluate_tree` marks itself live (`LiveWorkGate`, a counter, never a
      lock), and between features a warm banks the prefix it has built and waits
      for the worker to go idle, then reclaims its own checkpoint. Measured
      commit-immediately-after-open: N=50 2.0x worse -> +5 %, N=100 2.3x worse ->
      -2 %, N=200 2.1x worse -> +1.6 %. Banking is load-bearing — work a warm is
      still holding is invisible, so an unbanked pause cost a face pick the full
      9.2 s at N=100. [docs/PERF.md 2026-08-01b]

- [ ] (P3, S) **CONC-7 — nobody sized the connection pools, and the defaults
      are wrong in the direction that hurts** (backend). Neither pool is
      configured: `py_kit.db` takes SQLAlchemy's default 5+10 connections per
      service process, and `create_upstream_client` takes httpx's default 100
      max connections to geometry — i.e. the gateway will pile 100 requests onto
      a worker with one effective core. Nothing exhausted during the 2026-08-01
      run, so this is not a live defect; it is an undocumented default that
      makes CONC-2 worse and belongs in `docs/OPERATIONS.md` §6 with a number
      behind it. [docs/PERF.md 2026-08-01]

- [ ] (P3, S) **CONC-8 — editing a dimension under a picked-edge fillet fails
      `subshape_unresolved` on a 0.01 mm change** (kernel). Found while building
      the load harness, not looked for: on the `housing_tree(50)` tray, bumping
      the last `distance_mm` by 0.01 mm makes the picked-edge fillet that
      consumes that extrude fail to resolve its edge signature, so a valid part
      becomes a failed tree from a change no user would consider structural.
      This is the known stage-1 topological-naming limitation showing its edge,
      but the trigger is small enough to be worth a regression case and a better
      error message. [docs/PERF.md 2026-08-01]


Restocked 2026-07-23 (HEAD `0ed9f74`) — the overnight batch converged 18
Ready items (WF-1/PB-1 width extents, drawings dead-capability drain D1-D4,
MB-4c wire+frontend, e2e hardening) — all archived below (Done, one line
each). Fresh product-audit pass (2026-07-23) reframes assemblies as **"a
one-way street"** — buildable and solvable, but no export, no collision
check, no import — that gap now leads the queue (P0/P1). **Section views v1
SHIPPED** (kernel-architect, 2026-07-23): single planar full section of a
single-body part by principal / axis-aligned-offset datum reference —
`drawings/section.py` half-space cut + coplanar loops + `ComposedHatch` (ANSI-45°
even-odd scanline clip) across SVG/PDF/DXF, `views.section_params jsonb` (0008);
wrong-half + multi-loop + byte-determinism goldens; oblique + the `project_view`
frame refactor are v2/§11. Spike de-collected.

- [x] (P0, S) **LIC-1 — a GPL-2.0 library ships inside the OCP wheel and blocks
      the geometry image.** SHIPPED 2026-07-31 (platform-builder): jbigkit is
      replaced during the image build by a 16 KB MIT stub with the same file name
      and SONAME (`deploy/docker/licence/jbig-stub.c` + `strip-gpl-jbig.sh`,
      `--require` so a skipped strip fails the build). Proven inert, not assumed:
      the whole geometry suite ran against the stub — **2385 passed, 1 skipped**,
      goldens (stored content hashes = byte identity) included — boolean cut
      **5151.769984 mm³** vs the analytic value, STEP export byte-identical at
      19 020 bytes / 434 entities. `verify-kernel.py` re-proves it inside the
      build (mapped libjbig must be the stub; volume must be analytic), and
      `/app/licenses/` + OCI `image.licenses`/`.source` labels land with it
      (LIC-2's image half). docs/LICENSING.md §9. ORIGINAL FINDING: `libjbig` (jbigkit, GPL-2.0-or-later) is vendored by
      `cadquery-ocp-novtk` and hard-linked `libTKService → libfreeimage → libtiff
      → libjbig`; it maps into every process that imports the kernel. Violates the
      absolute "no GPL/AGPL" rule and would make a published geometry image
      GPL-2.0. Deleting it fails (eager binding: `undefined symbol: jbg_enc_out`);
      `libtiff` imports exactly 10 `jbg_*` symbols, and a GPL-free stub exporting
      them was BUILT AND VERIFIED 2026-07-31 — OCCT loads, boolean cut gives the
      analytic 5151.77 mm³, tessellation + STEP export fine. Apply in
      `deploy/docker/service.Dockerfile` after `uv sync`, with a build-time
      assertion that no GPL `.so` survives. docs/LICENSING.md §4.
      [oss-curator, platform-builder]
- [x] (P1, M) **LIC-2 — we redistribute LGPL binaries with none of their required
      text.** SHIPPED 2026-08-01 (platform-builder): the source half — the
      mirrored bundle is now one reviewed command, `just corresponding-source
      <tag>`, and NOTHING is published (founder's call; the script prints the
      `gh release upload` line instead of running it). Pinned in
      `deploy/licenses/corresponding-source.json`: OCCT 7.9.3 (git `V7_9_3`,
      commit `a016080`), planegcs 0.8.0 (PyPI sdist), LibRaw
      **0.19.5-1ubuntu1.4** — `.orig` **plus** the Ubuntu patch series, the old
      "0.19.5" would have been source that does not correspond. All five
      artefacts fetched and verified here: LibRaw digests equal Ubuntu's own
      `.dsc` stanza, planegcs equals the PyPI index and contains `GCS.cpp`, and
      three OCCT clone-and-pack runs gave byte-identical archives
      (`71c6a724…`). GitHub's release-asset URL is 403 here but `git clone`
      works, so no leg was left undone. `scripts/corresponding_source.py` is
      imported by BOTH the gate and the fetcher, so `just lint`, CI and the
      image build fail loudly on a wheel bump that moves a version out from
      under the pinned source — with negative controls in `just
      licence-selftest`. docs/LICENSING.md §7 (procedure) + §10. PRIOR
      2026-07-31 (platform-builder): the image half landed
      with LIC-1 — `/app/licenses/` now carries LICENSE, NOTICE, the five texts no
      wheel ships (LGPL-2.1, the OCCT exception, FTL, FIPL-1.0, MPL-2.0), a
      CORRESPONDING-SOURCE.md stating the §6(d) route and the §6(c) written offer,
      a THIRD-PARTY.md generated from the installed environment, and every licence
      file the wheels do ship; OCI `image.licenses`/`.source`/`.documentation`
      labels are set and the build FAILS if the licences label disagrees with the
      binaries present. ORIGINAL: The OCP wheel ships ZERO licence files (`RECORD` has no
      licen/copying/notice match across 398 entries) while carrying 68 LGPL-2.1
      OCCT libraries. LGPL-2.1 §6(b) does NOT cover us — clause (1) requires the
      library be "already present on the user's computer system", which is false
      for a container image — so we ship under §6(d)+(c): licence texts at
      `/app/licenses/`, `NOTICE` in the image, OCI `image.licenses`/`image.source`
      labels, and a mirrored corresponding-source bundle for OCCT 7.9.3 +
      planegcs 0.8.0. Checklist in docs/LICENSING.md §6. [oss-curator,
      platform-builder]
- [x] (P2, S) **LIC-3 — the licence gate must read bundled binaries, not wheel
      metadata.** SHIPPED 2026-07-31 (platform-builder): `scripts/check-licences.py`
      classifies all 96 loose `.so` files we ship from a written inventory
      (unknown library = failure), reads each binary's own licence strings, and
      parses ELF DT_NEEDED/dynsym itself so it runs in the runtime image (no
      binutils there). No false alarm on libgomp/libgfortran/libquadmath — GPL-3
      WITH the GCC Runtime Library Exception, each with a written reason. CI runs
      it (`licences` job, no daemon) plus a **self-test that proves it fails**:
      image profile against the real unstripped wheel must fail naming `libjbig`,
      then the production strip script, then must pass. Also in `just lint`.
      ORIGINAL FINDING: `cadquery-ocp-novtk` declares `License: Apache-2.0` and vendors
      GPL-2.0 + LGPL-2.1 code, so any metadata-only scan reports this tree as
      fully permissive — which is how LIC-1 survived to release week. Add a CI job
      that walks `*.dist-info` AND the vendored `.libs` trees (`readelf -d`), and
      re-runs on every OCP/OCCT bump: the vendored set is a property of the
      wheel's build machine and changes without notice. [oss-curator]
- [x] (P2, S) **LIC-4 — the GCC runtime libraries: decided, and all of them
      identified.** Done 2026-08-01 (platform-builder). DECISION: the GCC Runtime
      Library Exception discharges the source duty for the way we convey them —
      §1 permits propagating the Runtime Library combined with Independent
      Modules "under terms of your choice", and a combined work of Target Code is
      the only form Loft ever ships. Nothing is mirrored for them. The item's
      blocker was WRONG, which is the useful part: the exact GCC build IS
      derivable for every file (8, not 9 — the gate counts). `.comment` →
      conda-forge GCC 15.2.0-19 for OCP's `libgomp`; auditwheel SBOMs → AlmaLinux
      8 `gcc 8.5.0-28.el8_10.alma.1` (5 files); GNU **build-id** transfer → numpy's
      two (it ships no SBOM) are byte-identical builds to scipy's; one wheel
      further up → scipy's other pair came from scipy-openblas32, whose SBOM names
      CentOS 7 `libgfortran5 8.3.1-2.1.1.el7` + `libquadmath 4.8.5-44.el7`,
      confirmed by downloading that wheel and matching build-ids. No upstream
      GCC 8.3.1 exists, so an FSF tarball would have been the LibRaw-`.orig`
      mistake again. Ships: `GPL-3.0.txt` + `GCC-RUNTIME-LIBRARY-EXCEPTION-3.1.txt`
      (GCC's own copies, identical at all three tags), the reasoning + per-file
      table in `CORRESPONDING-SOURCE.md`, per-file records in the manifest's new
      `gcc_runtime` block, and a gate: `check-licences.py` reads each build-id and
      fails on any runtime library the manifest does not account for (4 negative
      controls in `just licence-selftest`). docs/LICENSING.md §7.5.
      [platform-builder]
- [x] (P2, S) **LIC-5 — `pnpm ... dev -- --port N` silently starts Vite on 5173.**
      Done 2026-07-31 (oss-curator, docs half). pnpm 10 DISCARDS the
      npm-idiomatic `--` separator, so the port argument never reaches vite and
      it falls back to `server.port` (5173) with no error — measured on 10.33.0;
      `dev --port N` and `exec vite --port N` both bind correctly. This is the
      origin of the stale-Vite trap that has poisoned a whole e2e suite before
      (`reuseExistingServer: true` makes the next `just e2e` reuse that stray
      5173, whose `/api` proxy points at a torn-down gateway → every spec 500s at
      seedSession). Correct invocations + the symptom are in docs/QUICKSTART.md.
      REMAINING: `apps/web/vite.config.ts` has no `server.strictPort`, so a
      dropped port silently falls back instead of failing — one line, app
      territory, for frontend-builder. [oss-curator]
- [x] (P1, M) **LIC-4 — the OSS front door was stale in both directions.** Done
      2026-07-31 (oss-curator): README claimed WebSocket fan-out (no WS routes
      exist anywhere), listed materials/mass, the settings surface and entity
      snapping as missing when all three had shipped, and pointed "next up" at
      Phase 1 while sitting past Phase 4b. The container-free run block omitted
      the `documents` service and every schema step, so a stranger following it
      got `503 database_unavailable` on registration — verified by running it.
      New docs/QUICKSTART.md (both paths, verified end to end natively: 9/9
      round-trip checks + browser → Vite → gateway → DB), honest PERF section,
      SECURITY.md's false "no authentication yet" corrected. [oss-curator]
- [x] (P1, L) **PERF-1 — `evaluate_tree` had NO rebuild cache, so every route
      re-ran the whole tree from feature 0.** SHIPPED 2026-07-31 (kernel-architect):
      `geometry/rebuild_cache.py`, a bounded thread-safe in-process LRU keyed on the
      rolling content hash of the feature PREFIX, holding the evaluator state.
      Entries are OWNED, not copied — a hit hands over the very shapes a cold
      rebuild would have built — because every re-materialisation of an OCCT shape
      (`BRepBuilderAPI_Copy` in all 4 flag combinations, BREP round-trip) keeps the
      volume bit-identical and still moves the GLB by a ULP, which would make
      `mesh_glb_id` depend on cache state. Serves APPEND + REPEAT; a mid-tree edit
      still misses (frontier-only checkpoints — PERF-1b filed). docs/PERF.md
      "2026-07-31c". [geometry-qa PERF-1]
- [x] (P0, M) **OPS-1 — there was no backup, no restore, and no restore test.**
      SHIPPED 2026-07-31 (platform-builder), the release blocker for self-hosting:
      Postgres holds every feature tree and a lost volume lost everything.
      `just backup` (both DBs, `pg_dump -Fc` online, manifest with alembic revision
      + exact per-table row counts + sha256, TOC-verified), `just restore`
      (works from nothing; `--single-transaction` so a failed restore leaves an
      EMPTY database instead of a half-populated one reported as success; re-checks
      revision + row counts against the manifest, exit 4 on drift), and version
      skew answered before anything is written — at head → nothing; ancestor →
      `MIGRATED <svc>: A -> B`; unknown revision (newer Loft) → REFUSED exit 3.
      Object storage deliberately NOT backed up (content-addressed derived
      artifacts; restore cost is one cold rebuild per part). Gate:
      `just backup-drill` / CI `backup-restore-drill` seeds real data, destroys
      the volumes (and asserts they are gone), restores, and demands the same
      volume AND the same `mesh_glb_id` from a re-evaluate. `docs/OPERATIONS.md`
      adds sizing: ~500 MiB OCCT baseline per geometry worker and a PER-PROCESS
      8-entry rebuild cache, so `--scale geometry=N` divides the hit rate.
      [founder / open-source release]
- [x] (P2, M) **PERF-1b — a mid-tree edit paid a full rebuild, and so did the
      first face pick after it.** SHIPPED 2026-08-01 (kernel-architect): prefetch on
      the only two genuine declarations of intent — an OPEN FEATURE EDITOR (warms
      the prefix before the edited feature, both lineages: the commit, then the
      pick) and the TIMELINE TRAVEL STOP (warms the shorter tree; only BACKWARD
      travel needs it, forward is an append the cache already serves). Measured on
      the tray: editing feature #192 of 200 is **33.7 → 4.8 s** commit and **34.7 →
      4.4 s** first pick; rolling the stop back to 100 features is **8.2 → 0.5 s
      (16x)**. A mid-tree edit at the halfway point gains only ~25 %, and that is
      the `N^1.85` curve, not the implementation (warming prefix k can remove at
      most `(k/N)^1.85`). Bounded and cancellable: ONE warm thread per worker (the
      DoS bound), 30 s shared budget in priority order, supersede + explicit
      cancel observed between features. A warm CANNOT publish — `WarmTreeResult`
      is a ticket and a boolean at both hops, and the gate asserts that after a
      warm the `mesh_glb_id` a real evaluate publishes does not resolve: no
      artifact exists to serve. docs/PERF.md "2026-08-01". [kernel-architect PERF-1]
- [x] (P1, M) **PERF-2 — the CM-6 validity gate was O(features x faces): 22 % of a
      big-part rebuild.** SHIPPED 2026-07-31 (kernel-architect): `_admit` now checks
      only the faces the op CREATED (`healing.new_geometry_is_valid`) — sound because
      OCCT shape identity is TShape identity, so an unchanged face cannot have
      changed verdict — keeping the whole-body check for a body being STARTED and at
      publish. Measured 21.5 → 6.3 ms per body-affecting feature at 219 faces, and
      flat in N. NOT taken: neighbour expansion (docs/PERF.md — one big top face
      borders every pocket, so it pulled in 71 % of the body and measured 27 %
      SLOWER) and `clean_shape`'s two GProp integrations (they bracket an in-place
      mutation; its toy-measured "~1.3 ms" docstring is corrected instead).
      [geometry-qa PERF-2]
- [x] (P1, M) **PERF-3 — STEP import of Loft's OWN export was at 92 % of the DoS
      ceiling. Done 2026-07-31 (kernel-architect).** Root cause was NOT a face-count
      law: OCCT's transfer runs `ShapeFix_Shape` after building the topology, and
      `ShapeFix_Wire::FixSelfIntersection` is super-quadratic in **edges per wire**
      (8/8 gdb stacks of a live 18 s import). The benchmark sink's comb faces carry
      ONE `4*fins+4`-edge wire, so its worst wire grew with the part. Disabling that
      one op (`FixShape.FixSelfIntersectionMode=0`, applied AFTER `ReadFile` or it is
      silently a no-op) gives **byte-identical** output and 2 006 faces **18.58 →
      3.46 CPU s** (5.4x), curve now linear. Ceiling stays 20 s, re-derived from the
      16 MiB upload cap: ~1.0 s fixed + **0.23-0.36 CPU s/MiB** → ~3x headroom at the
      cap, cliff at ~55 MiB, i.e. the upload cap binds first. docs/PERF.md
      "2026-07-31b". [geometry-qa PERF-3]
- [x] (P2, S) **PERF-4a — the mesh route shipped uncompressed** (no
      `GZipMiddleware` anywhere in geometry/gateway/py-kit). **Done 2026-07-31:**
      compression wired ONCE in py-kit `create_app`; measured on the real route
      1 117 KiB → **216 KiB** (tray N=200, 5.2x, +20.6 ms) and 1 064 KiB →
      **90 KiB** (2 006-face sink, 11.9x, +12.5 ms), `/openapi.json` 4.2x.
      `compresslevel=6` (Starlette's default 9 is strictly worse — more bytes,
      4-9x the CPU) and `minimum_size=1500` (one MTU; below it gzip cannot save a
      packet and `/healthz` gets *bigger*). The **gateway** is the hop that
      compresses: it buffers upstream bodies, so `create_upstream_client` now asks
      geometry for `identity` — that alone cut the end-to-end gateway fetch
      57.8 ms → **31.4 ms**. docs/PERF.md "PERF-4 landed". [platform-builder]
- [x] (P2, M) **PERF-4b — one glTF primitive per B-rep face (~425 B of JSON
      each). Done 2026-08-01 (kernel-architect), and CONDITIONAL, because always
      fusing is a wire REGRESSION.** Face ids ride a compact side table
      (`extras.LOFT_face_triangles`), not a vertex attribute — the partition is a
      run-length by construction, so it costs one int per FACE instead of 4 B per
      VERTEX. Sink 2 006 prims → **19**, 1 089 348 → **353 868** B raw but
      **91 837 → 45 086** gzipped (2.04x — report this one). The tray DECLINES:
      fusing re-bases indices and destroys the byte-identical local index runs
      deflate was matching, costing 2.2 gz-B/triangle against ~25 gz-B/face, so
      the first cut shipped it 23 % BIGGER on the wire. Break-even measured at
      ~20 triangles/face (threshold 12). Draw calls on a selected feature
      2 006 → **3** (tray 442 → 9) via material-run draw groups — that half
      helps both encodings. Browser GLB parse 47.2 → **3.4 ms**. Picking proven
      unmoved three ways (byte-identical per-face triangle streams; every
      triangle resolves to the pre-PERF-4b ordinal; equal face-ordinal checksums
      on both benchmark parts). Frame time NOT measured — no GPU here.
      docs/PERF.md "PERF-4b landed". [geometry-qa PERF-4]
- [x] (P2, M) **PERF-5a — per-face provenance went dark at ~103 features while its
      docstring said it never would. Done 2026-07-31 (kernel-architect).** Crossing
      point MEASURED, not bracketed: budget 7 242 at N=100, **8 180 at N=105**, so the
      old 8 000 ceiling was crossed at **N ~= 103** (~232 faces) — an ordinary
      authored part. `MAX_PROVENANCE_FACES` **8 000 → 30 000** (crosses at N ~= 207),
      re-derived from the measured 134-237 us/fingerprint: worst admitted pass
      ~4.0-7.1 s. The old ~1.5 s sizing was moot — at N=125, the first size 8 000
      refused, the same `/overlay` already pays ~11 s of rebuild and the pass is a
      steady **11-16 % of the request**, so the bound spent the point of the request
      to save a sixth of it. Still degrades the audit-H4 case (20 000-face import =
      budget 40 000). Gated by `test_provenance_budget.py`. [geometry-qa PERF-5]
- [x] (P2, M) **PERF-5b — attribution stops re-deriving what evaluation already
      knew. SHIPPED 2026-08-01** (kernel-architect). Evaluation now fingerprints each
      snapshot as it produces it (`FaceProvenanceRecorder` on `EvaluationState.
      provenance`) and retains `list[FaceFingerprint]`, not `list[BodyShape]`, so the
      interactive pass is `O(final faces)`: 108.5 → 13 ms at N=25 and **2 347 → 67 ms
      at N=150** (8.3-35x), and the "steady 11-16 % of the request" is **3.0-6.2 %**.
      A repeat face pick on the rebuild-cache hit — the one a working user gets — is
      1 238 → 185 ms at N=100, 2 667 → 435 at N=150. Two mechanisms: fingerprints
      instead of shapes, and a memo on OCCT shape identity (a boolean shares the
      `TShape` it did not touch — only **165 distinct faces** exist behind 1 930
      snapshot faces at N=50), without which the quadratic would merely have moved
      into the rebuild; the residual face WALK is raw `TopExp_Explorer` because
      `Shape.faces()` costs 10x it (229 vs 21.6 ms per 61 walks). Attribution proved
      IDENTICAL on 54 real parts / 1 573 faces (47 tree goldens + tray N=10..100 +
      heat sink 8/32/128) against the pre-change tree, and permanently gated by a
      memo-free replay, warm-vs-cold `FaceProvenance` equality, and operation-count
      gates. Retained memory 4.04 → 2.82 MiB per held evaluation at N=100. NO win on
      the FACE axis (3-feature heat sink: 1.0-1.1x — its pass was never quadratic),
      cold only 11-21 % better; both stated in docs/PERF.md. [geometry-qa PERF-5]

- [x] (P1, S) **Audit N4 tail — SET the export `name` at the callers. SHIPPED
      2026-08-01** (frontend-builder). Geometry had honoured an optional `name` on
      `ExportTreeRequest` / `ExportAssemblyRequest` since 2026-07-31; no caller set
      it, so every download still fell back to a uuid. Both sites now do. The
      gateway's `export_part` takes a SECOND auth-scoped documents fetch for the
      part header rather than the one-line spread the item assumed — the name is
      deliberately not on `EvaluateTreeRequest` (a name must never be an input to
      geometry, `DocumentName`), so there was nothing to spread; same reason the
      web passes it through `exportAssembly(request, format, name)` rather than
      through `buildEvaluateAssemblyRequest`, whose output feeds the SOLVE.
      Acceptance met against the exported bytes over the real three-service stack
      (`test_part_export_carries_the_part_name_end_to_end`): disposition
      `motor-mount-bracket.step`, `PRODUCT('Motor Mount Bracket')` present and
      `PRODUCT('SOLID')` absent, a sibling part downloads as `spindle-cap.step`
      (no Downloads collision), and a foreign caller still gets 404 with no name
      leaked. Browser-level: `full-flow` demands `baseplate.step`/`.stl`,
      `assembly-inspect` demands `bolted-plates.step` holding
      `PRODUCT('Bolted plates')`. [src: AUDIT-PRODUCT.md N4]

- [x] (P1, M) **#58 — the SETTINGS surface exists, and every row on it is wired.
      SHIPPED 2026-07-31** (frontend-builder, 2026-07-31; founder-raised "units and
      mass should be controlled from a settings page"). There was no settings
      surface at all — zero hits for settings/preferences across every route — so a
      user could not change the one binding CAD users have violent muscle memory
      about. `/settings` is now a sibling of the three registers (`SettingsSheet`,
      the register's drawer frame + the title block's field anatomy: control column
      left, CONSEQUENCE beside it, ruled to the frame edge), reached from the
      workspace switch. APPLICATION scope only, said on the sheet ("saved in this
      browser"): length unit for NEW documents (stamped by `createPart` /
      `createAssembly`, never a conversion), **scroll-to-zoom direction** (the
      founder-priority row — carried by the SIGN of the orbit rig's `zoomSpeed`,
      since it scales the radius by `0.95 ** zoomSpeed`; no event interception), and
      orbit / pan / zoom sensitivity as three named steps. Persisted like the
      session store (localStorage, per-field validation on load, injectable for
      tests); the viewport stamps the numbers it was handed
      (`data-nav-{rotate,pan,zoom}-speed`) so an unwired preference fails a spec.
      DELIBERATELY NOT RENDERED because nothing honours them yet: angular unit,
      display precision, grid/snap step, default material (filed below). 17 unit +
      6 component tests + `e2e/settings.spec.ts` (5, each asserting the effect on
      the surface that honours it, not the control). Shots
      `docs/screenshots/settings-after-{1440,1366}.png`.
      [src: founder #58 · ROADMAP "still queued: … a settings surface"]

- [x] (P1, L) **#WS1 — workspace management: search, sort, rename, duplicate,
      dependency-safe delete across all three registers. SHIPPED 2026-07-31**
      (frontend-builder; founder-raised "the row a user hits on their tenth
      document"). The three registers were create-and-open only: no way to find a
      document, reorder the drawer, correct a name, or copy one. Now, in the
      register's own title-block language and adding no floating chrome —
      **FILTER** is a ruled field on the header rule (`/` focuses, Escape or a
      quiet CLEAR empties it) filtering the whole drawer as you type, and the
      count becomes the FRACTION `4 of 12 parts` derived from the two arrays on
      screen so an empty result is legible instead of alarming; **SORT** is the
      column headers themselves (NAME numeric-collated so "Rib 2" precedes
      "Rib 10", LAST WORKED, FILED — `aria-sort` + a scribed chevron, default
      FILED-asc which IS documents' own order, ties left to the stable sort so the
      client never invents an order the server disagrees with); **RENAME** edits in
      the name cell under the document's OCC version (`tree_version` / `doc_version`
      -> 422 on a stale row) and the cell then renders what the refetched LIST says,
      never the typed string; **DUPLICATE** is a real endpoint per kind
      (`POST /{parts,assemblies,drawings}/{id}/duplicate`, `documents/duplicate.py`)
      — a part copies its WHOLE feature tree with every intra-tree id reference
      rewritten onto the copy plus dependency edges, travel stop, unit and
      materials; an assembly copies instances + mates rewired onto the copied
      instances but NOT the referenced parts; a drawing copies sheets/views/
      dimensions/annotations but not the referenced document. No copy inherits undo
      history or the last-evaluate record (a copy has never been built and its
      register row says `never`). The copy's NAME is the server's
      (`py_kit.schemas.workspace.copy_name`: "Bracket copy", "Bracket copy 2"…,
      truncating the base not the suffix) and the created document is returned, so
      the register never predicts it; **DELETE** now surfaces the existing
      409-with-dependents by NAME — the payload is a real DTO
      (`DocumentDependents`) DOCUMENTED as the delete routes' 409 response, so it
      reaches the generated TS client and the row lists "gearbox (assembly)"
      instead of "in use". 13 documents + 8 py-kit + 4 gateway + 37 component + 9
      api-layer tests (all mutation-verified) + `e2e/workspace.spec.ts` (4). Shots
      `docs/screenshots/workspace-register-{before-,}{1440,1366}.png` +
      `workspace-register-filtered-1440.png`. **FOLDERS REMAIN OPEN** and nothing
      on the surface pretends otherwise — filed below. [src: founder #WS1]

- [x] (P2, S) **F3 — deleting a feature warned about nothing; it now says WHO
      breaks, by name, before you commit. FIXED 2026-08-01** (frontend-builder).
      `deleteFeatureAction` fired straight off the context menu with no
      confirmation and no dependency check, and the refusal a user eventually met
      said "referenced by 2 other document(s)" — a sentence that ends the
      conversation. Now: the tree ASKS (`GET …/features/{id}/dependents`, a new
      route answered by the SAME documents-side query that builds the delete's
      409, so a warning and a refusal cannot disagree), and the confirmation
      either names what breaks — "Extrude1 (feature)", "Assembly sheet (drawing)"
      — and does not offer a delete the server would refuse, or says "nothing else
      depends on it, and Undo brings it back". The 409 payload is now a typed DTO
      (`FeatureDependents`) DOCUMENTED as the delete's 409 response, so it reaches
      the generated TS client; a race that 409s after a clean pre-check re-opens
      the confirmation with the refusal's own names. 3 documents + 2 gateway + 7
      component tests (mutation-verified) + `e2e/feature-delete-warning.spec.ts`.
      Shot `docs/screenshots/feature-delete-dependents-1440.png`.
      [src: docs/UI-REVIEW.md 2026-07-30 F3]

- [x] (P2, M) **F4 — a keyboard-first app with nowhere to learn the keyboard.
      FIXED 2026-08-01** (frontend-builder). `?` opens a KEY CARD from any authed
      surface. The point is not the overlay, it is that it CANNOT go stale: every
      row is derived, by one of three mechanisms, from what the handlers actually
      listen for. (a) The sketch tools, constraint verbs and view snaps are read
      off `TOOL_SHORTCUTS` / `CONSTRAINT_SHORTCUTS` / `CONSTRUCTION_SHORTCUT` /
      `VIEW_SHORTCUTS` — the very tables the handlers index, so a re-keyed tool
      re-keys the card. (b) Everything that used to be an inline string literal
      (the register's `N` and `/`, grid snap, measure, the seven part create
      letters) is now a constant in `shortcuts/registry.ts` that the page
      imports. (c) `V`/`⇧V` body isolation, whose handler is in another agent's
      territory, is pinned by a BEHAVIOURAL test that mounts the real hook, fires
      the key the registry declares and asserts the store moved — stronger than a
      shared constant, because it proves the key works rather than that two files
      agree about a string (mutation-verified: re-keying `KEY_ISOLATE` goes red).
      10 registry + 8 component tests + `e2e/shortcuts.spec.ts` (2), which reads a
      binding off the card and then FIRES it in the real app. Shots
      `docs/screenshots/shortcut-sheet-{1440,1366}.png`.
      [src: docs/UI-REVIEW.md 2026-07-30 F4]

- [x] (P2, L) **#WS2 — FOLDERS in the registers, backed by a real tree. SHIPPED
      2026-08-01** (frontend-builder). Four decisions, made explicitly and stated
      in `py_kit/schemas/folders.py`: (1) folders are **per-drawer** (`kind` on
      the row) because the registers are per-kind surfaces — a shared tree would
      put folders in the parts drawer holding no parts, and would force the count
      readout to lie or to report a number the drawer cannot show; (2) **"unfiled"
      is a real state** (`folder_id` NULLABLE), so every existing document stays
      reachable with no backfill and no per-owner root row to mint; (3) names are
      unique **per folder**, enforced by a PAIR of partial unique indexes because
      SQL treats NULLs as distinct and a plain composite UNIQUE would silently
      permit two *unfiled* "Bracket"s; (4) deleting a non-empty folder is
      **REFUSED and names its contents** — the same 409-with-contents grammar the
      document delete already uses, never a cascade (deletes documents nobody
      named) and never orphan-to-root (moves work invisibly). Ships `folders` +
      `folder_id` on all three document tables (`0015_folders`), a folders router
      with ancestor-walk cycle rejection and a depth bound, three `/move` routes
      that move neither the concurrency counter nor `updated_at` (filing is not an
      edit), and `folder_id` on the three CREATEs so filing inside a folder is ONE
      call. UI: folders are DIVIDERS in the log book (tab glyph in the scribed
      gutter, no rail — a rail would duplicate the breadcrumb), the breadcrumb IS
      the title, the filter searches the WHOLE drawer and labels each hit with
      where it lives (the reachability guarantee), and MOVE is a keyboard-first
      verb. 16 documents + 10 gateway + 11 component tests (mutation-verified:
      dropping the unfiled partial index, disabling the cycle check and skipping
      the delete refusal each go red) + `e2e/folders.spec.ts` (2). Shots
      `docs/screenshots/workspace-folders-{1440,1366}.png` +
      `workspace-folders-inside-1440.png`. [src: founder #WS1 scope item 5]

- [ ] (P3, S) **#WS3 — drag a register row onto a divider to file it.** #WS2
      shipped MOVE as a verb (a select of every folder by path) and deliberately
      did NOT ship drag: a filing gesture reachable only by pointer would put the
      product's one rearrangement out of keyboard reach, so the keyboard path had
      to be the primary one and is complete on its own. Drag is now purely
      additive — HTML5 dnd on `DocumentRegisterRow` with `RegisterFolderRow` as
      the drop target, calling the same `onMoveDocument`. Also open: moving a
      FOLDER (the endpoint and its cycle rejection exist and are tested; no UI
      calls `moveFolder` yet), and deep-linking the current folder into the URL so
      a folder view can be shared or reloaded in place. [src: #WS2 follow-up]

- [x] (P1, S) **The assembly panel stopped promising a mass it did not have — and
      the roll-up can now HAVE one. FIXED 2026-07-31** (frontend-builder,
      2026-07-31). `AssemblyInspector` carried a section headed **COMBINED MASS**
      over Volume / Area / Centroid and no mass: #57b's defect at a second address.
      The title is now earned (`Combined properties` until `mass_g` is real), the
      mass row formats through the one `formatMass` seam, a mass-weighted CENTRE OF
      MASS shows beside the volume centroid, and absence is stated in words naming
      the component that lacks a material — never `0 g`, and never blaming an
      instance whose part produced no body (that one never enters the roll-up).
      Found en route and fixed in the same slice: the browser's
      `buildEvaluateAssemblyRequest` never sent `EvaluatedInstance.materials`, so an
      assembly of fully-assigned parts came back `mass_g: null` FOREVER and the mass
      row was unreachable code; the request now carries each part's assignment and
      the evaluate key is stamped with the referenced parts' `tree_version` (a
      material edit does not bump the assembly's `doc_version`, so the cached
      evaluation outlived it). 7 unit + 6 component tests (mutation-verified) +
      `e2e/assembly-mass.spec.ts` driving a real assignment through the real stack.
      Shots `docs/screenshots/assembly-mass-{before,after}-1440.png`.
      [src: docs/design/materials.md §5/§6 · #57b, second address]

- [x] (P0, M) **QA-1 / CM-6 — a mirror shipped a body OCCT calls invalid, 3.48 %
      too heavy. FIXED 2026-07-30** (kernel-architect; QA wave `748a6ad`). Block →
      revolve-CUT groove straddling the XZ plane → body-scope mirror measured
      31,865.9587 mm³ against an analytic 30,793.62842102152, `is_valid` false, every
      feature `ok`, and it meshed, measured and exported to STEP. Not the mirror: the
      `fuse` is exact and valid, and the trigger is the groove's outer wall being
      exactly TANGENT to the block's own wall (measured — move it 0.5 mm and `clean()`
      behaves at every station). `Shape.clean()` welded the void shut. Fixes: (1)
      `healing.clean_shape` is now the ONE `clean()` call site and discards a
      simplification that moves material (bound measured over 3050 suite calls: worst
      1.6e-16 relative); (2) `BRepCheck` validity is asked at the three
      `EvaluationState` body funnels → typed `invalid_body`; (3) re-asked at publish
      time, because OCCT's boolean invalidates this body's ARGUMENT in place, and the
      artifacts are withheld rather than published wrong. Two hand-derived goldens
      (`mirror-revolve-groove-tangent-wall-40x40x10` + the clear-of-plane control that
      proves the fix discriminates), CM-6 matrix cases, kernel contract in
      `test_healing.py`. Cost +9…20 ms/rebuild, an order under the §9 ceiling.
      **Follow-up (apps/web, NOT this agent's territory): delete the `test.fail()` in
      `e2e/qa-wave-0730.spec.ts` "G" — the spec now passes, so it goes RED as filed.**
      [src: docs/QA-REVIEW.md 2026-07-30 QA-1 · GEOMETRY-QA 2026-07-30]
- [x] (P1, M) **QA-3 — a diameter dimension the revision never touched was
      destroyed. FIXED 2026-07-30** (kernel-architect; QA wave `748a6ad`). Tier-2
      circle re-anchoring keys on the 3-D centre, and a thickness edit slides a bore's
      rim along its own axis, so the Ø dimension went `unresolved` and left the sheet.
      Tier 3 frees the offset ALONG THE AXIS only (radius / axis line / angular
      station still pinned) and — because that alone cannot tell the two congruent
      rims of a through hole apart — scopes candidates to the model edges the
      dimension's own VIEW draws, the set the user could have picked from. Re-measures
      Ø10.000 at the new height; refusals kept for a moved hole, a coaxial counterbore,
      both-rims-drawn (ambiguous) and no-view-evidence. New revision gate asserts both
      dimensions in the exported SVG/PDF/DXF bytes.
      [src: docs/QA-REVIEW.md 2026-07-30 QA-3 · design drawings.md §3.5]
- [x] (P1, M) **QA-2 — a thickness revision destroyed every hole on the face.
      FIXED 2026-07-30** (kernel-architect; QA wave `748a6ad`). Retyping a bracket's
      thickness 10 → 16 orphaned `Hole1` (`subshape_unresolved`), stranded the three
      features after it and left a featureless 38,400 mm³ brick with the export
      blocked. Both face-matching tiers pin the PLANE; a depth edit translates it and
      changes nothing else. Third tier (`translated_signatures_match`,
      topological-naming.md §12) frees the offset along the normal and pins the
      normal SENSE, the area and the in-plane centroid — the sense being what stops a
      top-face hole re-anchoring onto the congruent bottom face. Bracket rebuilds
      6/6 ok at 227,397.93 mm³ (mirror-stage analytic dev 2.9e-11); first REVISION
      golden `revise-thickness-hole-on-moved-face-60x40x16`. Four shipped tests had
      encoded "the face is gone" as "the same face at a different z" — the very case
      this fixes — and were re-fixtured.
      [src: docs/QA-REVIEW.md 2026-07-30 QA-2 · GEOMETRY-QA 2026-07-30]
- [x] (P1, S) **QA-4 — a lost dimension leaves no trace on the print. FIXED
      2026-07-30** (kernel-architect; QA wave `748a6ad`). The composer SKIPPED any
      dimension it could not place (edge not drawn in that view, or drawn as a
      primitive the type cannot annotate) — it vanished from the sheet and from
      every export with no marker and no words, so a print missing a number read as
      a complete one. No skip branch now: every authored dimension lands, as its
      annotation or as a stamped `dimension_not_placeable` marker. Gates assert the
      EXPORTED BYTES through `POST /api/v1/drawing/compose` (SVG/PDF substrings,
      DXF read back with ezdxf, `placed == authored` count) — the caption function
      was already right; nothing called it on this path. Measured en route: the
      exported SVG DOES carry "REFERENCE LOST" for an unresolvable ref (QA-4's
      export claim not reproducible); the silent surface is the on-screen sheet,
      which still draws the pre-N1 bare `!` — filed for the frontend owner below.
      [src: docs/QA-REVIEW.md 2026-07-30 QA-4 · design drawings.md §3.4]
- [x] (P1, S) **QA-4b — the on-screen sheet says what the export says. FIXED
      2026-07-31** (frontend-builder, 2026-07-31). `DimensionGlyph` drew a 2.6 mm
      dashed circle holding a bare `!` and dropped the `message`/`text` the
      composer has carried since `7fde5d2`, so the engineer at the screen was told
      less than the machinist holding the PDF. The caption is now stamped at
      `dim.text` in the SERVER's words (no client-side phrase table) at the
      composer's own cap height — a new `drawing.dimensionErrorTextMm` token
      mirroring `_DIM_ERROR_TEXT_MM`, the same cross-renderer rule `noteTextMm`
      carries — and the `<title>` spends it too. The stale QA-4 repro (revise a
      thickness, which QA-3 made survivable) is rewritten to a genuine loss: the
      hole is deleted from the sketch its edge came from, and one spec now asserts
      the SAME sentence on the sheet and in the exported SVG. Shots
      `docs/screenshots/drawing-dim-lost-{before,after}-1440.png`.
      [src: docs/QA-REVIEW.md 2026-07-30 QA-4]
- [x] (P1, L) **#57 — MASS PROPERTIES can report MASS. Kernel + wire SHIPPED
      2026-07-30** (kernel-architect; founder-raised "units and mass should be
      controlled from a settings page"; design `docs/design/materials.md`,
      decision RESEARCH §9a, numbers GEOMETRY-QA 2026-07-30). The panel was named
      for a thing it did not have: no density, no material, anywhere — and
      `ShapeProperties.centroid` was even documented as "centre of mass". Now:
      a 7-material handbook library in `py_kit.schemas.materials` (served at
      `GET /api/v1/materials`, never hardcoded client-side); `mass = volume x
      density` derived in `measure_shape` beside the volume it comes from;
      assignment = document default + per-body overrides keyed by the §MB-0 base
      feature id (`parts.materials` JSONB, migration 0013, wholesale PATCH
      replacement) threaded through the part AND assembly evaluation requests.
      **Absence is the contract:** no material -> `mass_g: null`, never 0 g and
      never a defaulted steel; 45 goldens assert it. Both analytic roll-ups
      compose mass and a genuinely MASS-weighted `center_of_mass` (the assembly
      had been calling its volume weighting mass-weighted): measured 27.0 g
      (dev 3.6e-15) single-material, **84.56 g at x=32.3368 mm vs the volume
      centroid's 25 mm** mixed. GLB bytes identical with and without a material.
      A material change marks the last-evaluate record stale (mass depends on
      it), unlike a rename/unit change. FRONTEND FOLLOW-UP filed below.
      [src: founder flow audit 2026-07-30 · UI-REVIEW "overstated surface" class]
- [x] (P1, M) **#57b — the mass UI: stop promising mass before there is a
      material. SHIPPED 2026-07-30** (frontend-builder). The panel is titled
      PROPERTIES with NO mass row while `properties.mass_g` is null and earns
      MASS PROPERTIES only when a material gives it one; absence reads as the
      MATERIAL cell's "No material" + "Assign a material to get a mass", never
      `0 g`. Picker + density come from `GET /api/v1/materials` through the
      gateway (nothing client-side knows a density); assignment PATCHes
      `materials` wholesale under `expected_tree_version` (document default +
      per-body override rows), retrying once on a stale-version race. Mass rides
      the ONE units seam (`MASS_G_PER_UNIT` / `formatMass` in
      `packages/design/src/units.ts`): 21.6 g on a 20 mm aluminium cube, 0.1388
      lb in an inch document, g->kg above 1000 g. A mixed part shows CENTRE OF
      MASS apart from the centroid (measured on screen: 32.34 vs 25 mm on the
      84.56 g two-cube part) and NAMES the body with no material
      ("Extrude2 has no material, so the part has no total mass.") instead of
      going quiet. 42 unit/component tests (mutation-verified) +
      `e2e/materials.spec.ts` (6, real OCCT); shots
      `docs/screenshots/materials-{before,after,after-assigned}-{1440,1366}.png`
      + `materials-after-mixed-1440.png`. Original acceptance: (1) while `properties.mass_g` is null the
      panel is NOT titled "MASS PROPERTIES" and shows no mass row — it offers the
      assign-material affordance instead; (2) absence renders as absence (an em
      dash / "no material"), never `0 g`; (3) a material picker reading
      `GET /api/v1/materials` (document default + per-body override on the Bodies
      panel, PATCH `materials` wholesale with `expected_tree_version`); (4) mass
      formats through the SAME units seam lengths use — `MASS_G_PER_UNIT` +
      `formatMass(g, lengthUnit)` in `packages/design/src/units.ts`, imperial
      documents reading lb, metric promoting g->kg above 1000 g (materials.md §5);
      (5) a mixed-material part shows the centre of MASS distinctly from the
      centroid, and names the body that has no material when the part total is
      null (`BodyLumpInfo.material`/`.mass_g` carry it). [src: materials.md §6]
      UNBLOCKED 2026-07-30 (backend-builder): `GET /api/v1/materials` now has its
      GATEWAY twin (`gateway/materials.py`, auth-gated proxy) — the picker in (3)
      reads it through the gateway instead of 404-ing or reaching past it.
- [x] (P1, M) **UI-W1 — the bottom TIMELINE strip with a draggable travel stop.
      SHIPPED 2026-07-30** (frontend-builder; founder-directed, design
      `docs/design/ui-wave-tool-grade.md` Surface 1). Rollback left the tree
      panel's 1px `ROLLBACK` rule for a docked 48px machine way: verb-glyph op
      chips + tabular ordinals, solid way through travelled ops and dashed past
      the stop, and a brass travel stop that drags AND arrow-keys (`role=slider`,
      Home/End, focus follows the move) with `TO TIP` as the escape hatch. Chips
      dim as well as dash; error = `flag`, suppressed = the tree's struck-through
      treatment. DRY: `features/rollback.ts` ported to the horizontal axis
      unchanged, ONE `VERB_GLYPHS` map now feeds the command band and the timeline
      (`CreateStrip` converted, drift-guarded), `BandActionCell` extracted as a
      shared primitive. The design system's last target-size exception (the 8px
      drop slots) is retired — every rollback control is 24x47, asserted. All
      `rollback-slot-N` hooks preserved; `timeline.spec.ts` (7) + 50 regression
      specs green; founder shots `timeline-{before,after}-{1440,1366}.png`.
      [src: founder directive 2026-07-30 · ROADMAP current focus]
- [x] (P1, L) **UI-W3 + UI-W4 — the cursor's selection prefills the editor, and
      an editor's references stop scrolling away. SHIPPED 2026-07-30**
      (frontend-builder; founder-directed "placement face looks like a text box?
      Shouldn't it know based on the face I select with the cursor?", design
      `ui-wave-tool-grade.md` Surface 3). `features/preselect.ts` keeps a pick
      alive past the command that made it; hole / datum / sketch-on-face /
      shell / draft / fillet / chamfer / edge-flange / hem all seed from it, and
      a pick is withheld once the body it was taken from is no longer the tip
      (anchor-scoped, so a stale signature never prefills an unresolvable ref).
      Invoking Hole with nothing selected ARMS the face pick — arming is now for
      CHANGING a reference. The picked faces stay LIT with no editor open.
      UI-W4: references pinned in an `EditorCard.header` anchor block, Ø as
      `NumberField emphasis="primary"`, the thread block behind a new
      `Disclosure` primitive that reports its callout when shut, and the card
      docked to the right rail clear of the reference cube. Web unit 1087 +
      design 54; `preselection.spec.ts` + 18 hole specs + 12 regression specs
      green on a live stack; shots `uiw34-hole-{before,after}-{1440,1366}.png`.
      [src: founder report 2026-07-30 · ROADMAP current focus]
- [x] (P1, M) **UI-W2 — per-instance visibility, opacity and isolate. ASSEMBLY
      HALF SHIPPED 2026-07-30** (frontend-builder; founder-directed "what about
      different components enablement, opacity, etc.", design
      `ui-wave-tool-grade.md` Surface 2). The product audit measured a
      21-instance assembly with no way to see inside it. Each component row
      carries an EYE drawn in our hand (three forms differing by whole strokes,
      after a hollow-vs-filled pupil measured illegible at 16px); the addressed
      row discloses SOLID · GHOST · HIDE (`SegmentedControl`, quantized — the
      320px row cannot hold a slider, and a hover-revealed control would reflow
      the list under the cursor); ISOLATE is a right-click verb with `V` / `⇧V`,
      `⇧V` doubling as the way back so no chord can strand you. Mandate 3c is
      asserted on canvas PIXELS (luminance-banded census; mutation-verified to
      fail when the WebGL wiring is stubbed). Hidden = nothing drawn (body, pool,
      balloon, mate overlay) and out of the camera-fit bounds. GHOST references
      the existing `viewport.preview` translucency but NOT its brass tint. View
      state is client-only — the solve, the clash check and exports are
      unchanged. The `ISOLATED` `Stamp` is DERIVED, renders only while something
      is hidden, and is pointer-inert but for its control. Web unit 1140 + design
      63; `assembly-visibility.spec.ts` (6) + 18 regression specs green on a live
      native stack; shots `uiw2-visibility-before-{1440,1366}.png`,
      `uiw2-{ghost,isolate}-{1440,1366}.png`. **PART HALF SHIPPED 2026-07-31**
      (frontend-builder; founder: "what about the ability to enable planes,
      sketches and bodies? Similar to fusion?"). Same vocabulary, three
      categories: SKETCHES + ORIGIN sections in the browser, eyes + the
      SOLID · GHOST · HIDE control on the Bodies list, `V` / `⇧V`, the derived
      `ISOLATED` stamp. The origin planes and axes had never rendered AT ALL, so
      every datum decision was made against geometry you could not see; they now
      draw in the plane-picker's own tokens, sized 1.6x the subject so a sheet is
      not hidden by the part it passes through, axes solid on + and phantom on −.
      Four as-built corrections in the design doc: two stops (not three) on rows
      where GHOST would mean nothing; disclosure on ADDRESSED not SELECTED
      (selecting a body row opens its base feature's EDITOR — measured, the ghost
      shot came back with the extrude editor open); a sketch's stop is DERIVED
      from "does a body exist" with an explicit override either way; and per-body
      hiding is recovered from the ONE fused GLB by connected components +
      the per-body lump count (`bodyPartition.ts`), withheld with a reason rather
      than guessing when the arithmetic does not line up. Web unit 1283 + design
      66; `part-visibility.spec.ts` (7) + `view-fit.spec.ts` (5) + ~230 regression
      specs green on a live native stack; mutation-verified — stubbing the WebGL
      side fails 4 of 5 pixel tests while aria/`data-*` still flip. Shots
      `uiw2-part-{origin,hidden,ghost}-after-{1440,1366}.png`.
      [src: founder directive 2026-07-30 · AUDIT-PRODUCT 21-instance assembly]
- [x] (P1, M) **UI-W5 — entity snapping in the sketcher, with a mark that says
      WHICH snap you are about to take. SHIPPED 2026-07-31**
      (frontend-builder; founder question "what about snapping to a face or
      point? With control or command?"). The sketcher had ONE snap — a grid
      hardcoded at 1 mm. Now `sketch/snap.ts` resolves endpoint / midpoint /
      centre / intersection / tangent / perpendicular-foot analytically (exact
      line/circle/arc crossings, not chord approximations; splines fall back to
      the sampled ink), Shift locks the aim to an axis through the placement
      anchor, and the grid step is a store value (`snapStepMm` / `setSnapStep`)
      for the settings surface rather than a literal. **Polarity is inverted
      from the phrasing on purpose: snapping is ON and Ctrl/Cmd SUPPRESSES it**
      (all of it, grid included) — a precision you must hold a key to reach is
      one a novice never finds; Alt is avoided (window managers fight for it).
      The honesty half: a mark at the candidate names it before the click, four
      new glyphs differing by WHOLE STROKES (square / triangle / circled cross /
      bare X — a fill difference is not a difference at 16px), tangent and
      perpendicular reusing the constraint glyphs of the same names. Measured,
      not eyeballed: mark `brass-hover` on carbide 11.80:1, 5.49:1 worst case
      over a major grid line; the word `mist` on anvil 13.21:1. The crosshair
      stands down while a mark is up (it was poking through every form). e2e
      proves the chain end-to-end — with the grid OFF, a click 6 px off a corner
      persists as exactly (40, 25). web unit 1218 + design 66;
      `sketch-snap.spec.ts` (6) + 55 sketch/flow regression specs green on a
      live native stack; shots `uiw5-snap-before-{1440,1366}.png` and
      `uiw5-snap-{endpoint,midpoint,center,intersection}-{1440,1366}.png`.
      [src: founder question 2026-07-30 · ROADMAP current focus]
- [x] (P1, M) **UI-REVIEW 2026-07-30 P1/P2/P3 — the export strip's second fold
      regression, the timeline's false redundancy claims, and three silent
      gates. FIXED 2026-07-30** (frontend-builder, folded into UI-W3/W4).
      `FloatingPanel.footer` PINS the export strip so a clamped panel can never
      push it (or its *partial* warning) under the fold — measured guard in
      `body-status.spec.ts`, which reports `clipped by …` on the old layout.
      Timeline chip border `hairline`→`etch` (1.54:1 → 3.06:1); the lifted-seat
      claim corrected rather than restated; the in-flight rollback's stop, drop
      slots and TO TIP now LOOK gated (`aria-disabled`, no grab cursor, honest
      caption); `BandActionCell`'s reason off `opacity-40` + off `text-[9px]`;
      chip `title`; Escape aborts a stop drag; `exportGate` blames the travel
      stop instead of "No body". Plus, found while verifying: a gated
      `PanelActionCell` keeps pointer events, so an editor card over the model
      made the edge beneath it UNPICKABLE (reproduced at HEAD) — fillet/chamfer
      take the right rail while picking. [src: docs/UI-REVIEW.md 2026-07-30]
- [x] (P0, S) **CM-1 — a `mirror` re-ERASED a cut when ANY non-cut feature sat
      between the cut and the mirror. Fixed 2026-07-25.** Cut tools are now
      TRACKED PER FEATURE (`EvaluationState.record_cut_tools`, with the producing
      feature id and body id) and read by two documented rules over one store:
      `_mirror_cut_tools` = the most recent cut of the active body (CM-1),
      `_pattern_cut_tools` = only the immediate predecessor (the pattern's locked
      rule — its fallback loses a reading, not geometry). Also closes a latent
      multi-body hole: a cut in body A can no longer be reflected into body B.
      Measured: chamfer 31640.0 -> **29629.3807**, fillet 31845.4867 ->
      **29834.8674**, both bores present (12 faces). `xfail` removed for those two
      params; +3 guards in `test_mirror.py`.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P2, L) **Mirror v2 — mirror a SELECTED SET of features. SHIPPED
      2026-07-30** (kernel; design `docs/design/mirror-semantics.md`). CM-1's
      re-scoped residual is closed by the CONTRACT, not a cleverer heuristic:
      `MirrorParamsV1.scope` is a `kind`-union (`body` = v1 verbatim, `features` =
      an explicit tree-ordered selection). Measured, all four: **30629.3807**
      (`features: [hole, boss]`), **30309.3807** (the same chain with no `scope` —
      the locked `body` reading), **29600.0** (both spellings agree),
      **28800.0** (`features: [A, B]`). `body`-path byte identity VERIFIED not
      assumed: all **39** goldens' GLB sha256 + metadata identical to the pre-v2
      kernel. New codes `mirror_feature_unsupported` / `_unreachable` /
      `_other_body` / `_not_evaluated`; 3 new goldens; matrix verb
      `mirror_features` (+8 cells, 112 asserted); `test_mirror_features.py` (33).
      One documented divergence: a SUPPRESSED selected feature is
      `references_suppressed` (the generic ref rule) rather than design §8.2's
      "skip silently" — locked with its reasoning in
      `test_a_suppressed_selection_is_references_suppressed`. Follow-ups filed
      below (web authoring; the v1 cut slot's own coverage gap).
      Original acceptance criteria, all met:
      (1) `MirrorParamsV1` gains `scope`, a `kind`-discriminated union — `body`
      (v1, **retained verbatim**: absent key normalises via a before-validator, so
      `param_version` stays 1 and every shipped mirror golden is byte-identical
      *structurally*, on unchanged code) and `features` (`list[FeatureRef]`,
      `min_length=1`, duplicates = 422); `FeatureRef` so each selection
      materialises into `feature_dependencies` (409-with-dependents +
      strict-backward + body-affecting-target 422 for free).
      (2) `record_cut_tools` widens to `op`-tagged, **opt-in** per-feature tool
      recording (only ids a `features` mirror names retain tools — the
      `body_history`/H4 posture, so trees without one pay nothing); **both v1
      readers (`_mirror_cut_tools`, `_pattern_cut_tools`) must return the SAME
      tools after the widening** — the highest-risk hunk — proven by the unchanged
      goldens + `test_mirror.py`/`test_pattern.py` locks; also close the store's
      coverage gaps (today only extrude-cut + hole record: add revolve/sweep/loft
      cut, every additive verb, and `pattern`).
      (3) Per-kind dispatch: reflect the recorded rigid tool + re-apply that
      feature's own boolean, in **tree order** (never array order — RESEARCH §9).
      In scope: additive extrude/revolve/sweep/loft/import, all cuts, all four
      hole types, `pattern` (reflect PLACEMENTS not params — chirality), nested
      `features`-scope mirror. Typed refusals (`mirror_feature_unsupported` /
      `_unreachable` / `_other_body` / `_not_evaluated`): fillet/chamfer/shell/
      draft + sheet-metal folds (no rigid tool — a reflected delta-sliver is
      silent-wrong-geometry), `body`-scope nested mirror, cross-body, boolean,
      non-body-affecting. A reflected cut that removes nothing is now an ERROR,
      not v1's union fallback (explicit intent buys honesty).
      (4) Three new goldens: `mirror-features-hole-boss-plate-40x40x20`
      (**30629.3807**, CURVED_TOL), `mirror-features-pocket-b-only-40x40x20`
      (**29600.0**, 21 faces, PLANAR_TOL), `mirror-features-both-pockets-40x40x20`
      (**28800.0**, PLANAR_TOL) — no new epsilon.
      (5) `CM1_BOSS_UNMIRRORED` is cleared by **giving the case an explicit
      selection**, not by a silent green: it splits into a selection variant
      asserting 30629.3807 (marker removed) + an implicit variant asserting
      30309.3807 as the locked `body`-scope semantic. Read `mirror-semantics.md`
      §5 before touching the marker.
      **Correction to this item's earlier text (STILL TRUE after shipping):** v2
      does **NOT** retire the "a crossing mirror erases an asymmetric modifier"
      limit — a modifier cannot be named in a selection (design §4.3/§10.1), and
      `test_observed_limit_a_crossing_mirror_erases_an_asymmetric_modifier` stays
      green and unedited. Also not solved: symbolic "mirror image of face F" refs,
      extent-derived tools, sheet-metal/assembly mirror.
      [src: CM-1 fix 2026-07-25; design 2026-07-29; shipped 2026-07-30]

- [ ] (P2, M) **Web authoring for the mirror scope** (frontend; unblocked by the
      kernel above). Two radio buttons ("Mirror: body / features") plus a
      feature-tree multi-select; `scope` is OPTIONAL in the generated client
      (`scope?: MirrorBodyScope | MirrorFeaturesScope`), so existing callers are
      unchanged and only the new UI sends it. Surface the four typed refusals by
      `upstream_feature_id` (the offending SELECTED feature, so the tree row is
      highlighted, not the mirror). Defaulting the UI to `features` while the
      schema defaults to `body` is legitimate and probably right (design §11.2).
      Open UX question §11.4: warn when a selected feature is suppressed — today
      that is a typed `references_suppressed` error, so the warning is a
      pre-flight nicety, not a correctness gap.
      [src: mirror-semantics §11.2/§11.4]

- [ ] (P3, S) **The v1 cut slot still records only extrude-cut + hole.** v2's
      per-feature store covers every mirrorable verb, but `record_cut_tools` —
      which `body`-scope mirror and `pattern` read — was deliberately NOT widened
      (mirror-semantics §6.2: doing so silently changes what those two reflect on
      trees with shipped goldens). Consequence: a `body`-scope mirror after a
      revolve/sweep/loft CUT still takes the reflect-and-union path and can fill
      that void — the FINDINGS #2 class, for the three non-extrude cuts. Fixing it
      is a real behaviour change needing its own goldens; the `features` scope
      already gives users a correct answer today.
      [src: mirror v2 implementation 2026-07-30]

- [x] (P2, M) **"Is broken" on the parts register — BACKEND SHIPPED 2026-07-30**
      (backend-builder; design `docs/design/feature-tree.md` §4.4a). The one
      column the 07-30 UI review argued back in. Migration `0012` adds nullable
      `parts.last_eval_status` / `last_eval_at` / **`last_eval_tree_version`**,
      and `PartResponse` serves a derived `eval_state` of
      `never` / `ok` / `failed` / `stale` — the fourth state exists because a
      bare status is a claim about a tree that moved (the stored-BOM-number
      failure mode, `drawings.md` §8a.1), so staleness is derivable at the API,
      not guessed from `updated_at > last_eval_at`. The **gateway** writes it
      after a successful evaluate (a client-reported status is forgeable and this
      lands on a dashboard), in a background task with all failures logged and
      dropped — bookkeeping never slows or fails an evaluate. Monotonic in
      `tree_version`; does not move `updated_at`; carried forward across a
      rename/re-unit. 13 documents + 6 gateway + 2 migration tests; list endpoint
      asserted still ONE query. Parts only — assemblies/drawings filed below.
      [src: UI-REVIEW 2026-07-30 verdict 1]

- [x] (P2, S) **Register column for `eval_state` — SHIPPED 2026-07-30**
      (frontend-builder). Its OWN column (REBUILD), adjacent to LAST WORKED
      rather than inside it: the two answer different questions and are both
      worth saying at once ("20 min ago" + "broken"), and sharing the cell would
      have quietly redefined LAST WORKED, which the backend protected by not
      bumping `updated_at`. Four states, no client-side derivation (`eval_state`
      is read, never recomputed): `—` + sr-only "not evaluated" for `never`;
      quiet CLEAN for `ok`, whose title states it is not a claim of a body; a
      flag-inked BROKEN stamp for `failed`; and for `stale` the dashed
      indeterminate stamp the clash schedule uses for UNVERIFIED, spending the
      raw record in past tense (WAS BROKEN / WAS CLEAN) so it says more than
      "unknown" without dressing it up as current. New `Stamp` primitive is that
      one vocabulary (extracted on its third use). Evidence:
      `docs/screenshots/register-health-{before,after}-{1440,1280}.png`;
      `e2e/p2-register-health.spec.ts` produces all four states from the REAL
      stack (OCCT really fails the r50 fillet). [src: UI-REVIEW 2026-07-30
      verdict 1]

- [x] (P2, S) **F2 — "Up to date" was computed from request state, not from
      staleness: the WIRE half SHIPPED 2026-07-30** (backend-builder).
      `PartPage`'s `BodyStatus` says "up-to-date" whenever no request is in flight
      and the last one did not error — which is NOT the claim "the body you are
      looking at was built from the current tree", and under a concurrent edit
      (nothing invalidates) it asserts currency indefinitely. Provenance is now
      derivable at the API instead of inferred: `PartResponse.tree_version` serves
      the part's CURRENT counter (the staleness DENOMINATOR, mirroring
      `AssemblyResponse.doc_version` — the part header row was the only document
      header missing its own version, so a client had to download a whole feature
      tree to learn it), and `EvaluateTreeResult.tree_version` is now DOCUMENTED as
      the version the returned body/mesh was BUILT FROM (already echoed, but
      described as a "cache/correlation key", which entitles no truth claim). The
      comparison is ONE py-kit function — `is_stale_for_tree`, which
      `derive_part_eval_state` now folds through — so the register's four-state
      verdict and a body readout cannot drift apart on what "stale" means. Purely
      additive: no migration (the column exists), no new route, no new REQUEST
      field; the one new required RESPONSE field's two Python constructors ship in
      the same commit. 10 py-kit + 2 documents + 1 gateway regressions; contracts +
      ts-client regenerated. [src: UI-REVIEW 2026-07-30 F2, re-scoped]

- [x] (P1, M) **J3 — a verdict on a ROLLBACK PREFIX stops reading as a verdict on
      the part. WIRE SHIPPED 2026-07-30** (backend-builder). Documents applies the
      travel stop before the evaluate request leaves, so a part rolled back to
      feature 2 of 9 evaluated two features, succeeded, recorded `ok` and the
      register said **"Clean"** — about seven features nobody looked at. Fixed as a
      SECOND, ORTHOGONAL axis (`PartResponse.eval_scope`: `whole`/`rolled_back`/
      null), not a fifth state: the two combine (a rolled-back tree can also fail)
      and the asymmetry is real — a `failed` prefix still means broken, an `ok`
      prefix does not mean it builds. `derive_part_eval_state` stays the single
      state fold; `derive_part_eval_scope` consumes its output. DOCUMENTS derives
      it at record time (`parts.last_eval_scope`, migration `0014`) — the gateway
      never learns rollback exists, so `PartEvaluationRecord` gains no field and no
      caller broke; `eval_scope` is optional on the wire, so `apps/web` typechecks
      untouched. A bar on the LAST feature reads `whole` (hedging a part that did
      build is the mirror-image lie). 8 documents + 5 py-kit + 2 migration tests,
      each mutation-verified; the audit's `grep -c rollback` → 0 gap is closed.
      FRONTEND FOLLOW-UP filed below. [src: AUDIT-ENGINEERING J3]
- [x] (P1, S) **J3b — the register cell SPENDS the scope the wire carries. FIXED
      2026-07-31** (frontend-builder, 2026-07-31). A part rolled back to feature 2
      of 9 read **Clean** in the drawer — a verdict on a prefix printed as a verdict
      on the part. `HealthCell` is now a renderer over `registerHealthReadout` in
      `features/partBuild.ts` (the same module the open part's SOLVE/STATUS/EXPORT
      cells read, so the drawer and the workspace cannot drift): `ok` +
      `rolled_back` reads **"Clean to stop"** in the dashed indeterminate stamp the
      product already uses for "not established", `failed` + `rolled_back` still
      reads Broken with the stop named in its title, and `eval_scope: null` renders
      byte-identically to before — null is unqualified, never `whole`. A stop on the
      LAST feature comes back `whole` and is NOT hedged. `data-health` stays the
      state; `data-health-scope` carries the second axis. 7 unit + 1 component test
      (mutation-verified) + an e2e that parks a real travel stop through the
      rollback route. Shots `docs/screenshots/register-scope-{before,after}-1440.png`.
      [src: AUDIT-ENGINEERING J3, wire half shipped above]

- [x] (P1, M) **J2 + N3 + F2-frontend — the part workspace stopped asserting what
      it did not know. SHIPPED 2026-07-30** (frontend-builder; one slice, because
      they were one defect seen from three cells). ONE derivation
      (`apps/web/src/features/partBuild.ts`) now feeds SOLVE, STATUS, EXPORT, the
      SKIP rows and a viewport notice, over provenance (`EvaluateTreeResult
      .tree_version` vs `PartResponse.tree_version`, the shared `is_stale_for_tree`
      rule from `7d0ba8e`) instead of three local expressions over `isFetching`.
      Export REFUSES a broken tree naming the feature to fix (it used to say
      "Ready" and hand over a STEP of the last-good PREFIX — the harm, not just
      the label); a DELIBERATE travel stop still exports, marked `Partial` in the
      cell AND `-partial` in the filename; unverified provenance waits for the
      rebuild. `last_good_feature_id` is finally consumed ("built to Extrude1"),
      and every SKIP row names its blocker so an independent fillet vanishing no
      longer reads as a fillet bug. The part query lost `staleTime: Infinity` so
      the client can LEARN the tree moved. 30 tests (mutation-verified: reverting
      any single derivation fails its own named test) + `e2e/body-status.spec.ts`
      (5, real OCCT r50-fillet failure) — the four pre-existing `body-status`
      assertions were all happy-path, which is why this shipped. Shots
      `docs/screenshots/body-status-{before,after}-{1440,1366}.png`.
      [src: AUDIT-ENGINEERING J2, AUDIT-PRODUCT N3, UI-REVIEW 2026-07-30 F2]

- [x] (P2, XS) **The register's sheet number claimed a filing identity and was a
      row ordinal — FIXED 2026-07-30** (frontend-builder). `001/002/003`, doc-
      commented "filing identity: stable", computed `String(index+1).padStart(3)`:
      delete row 1 and `001/002` address different parts, so a user who cited
      "sheet 002" in a change note held a reference that silently retargeted.
      The number is a POSITION and is now presented as one — `#` header with an
      `sr-only` "Row" (the bare `№` glyph also announced as "numero sign"),
      unpadded, `part-ordinal` hook. Form unchanged. e2e proves the renumber
      against a real delete. [src: UI-REVIEW 2026-07-30 P2]

- [ ] (P3, M) **Real sheet numbers: a stored per-owner monotonic sequence.** The
      honest fix above keeps the gutter truthful but a drawing register arguably
      wants a durable sheet number a person can cite across deletes — that is a
      `documents` column + backfill (assign on insert, never reuse), plus a
      decision on whether it is per-owner or per-project. Only worth building if
      the founder wants citable sheet numbers; the ordinal is not a placeholder
      for it, it is a different, correct thing. [src: UI-REVIEW 2026-07-30 P2]

- [ ] (P3, S) **Same last-evaluate record for assemblies + drawings.** Parts got
      `0012`; the assembly and drawing registers still cannot say "is broken".
      Assemblies have their own evaluation-request path, so the pattern ports
      directly (`doc_version` in place of `tree_version`); a drawing's health is
      really its source documents' plus compose, so decide what it claims before
      building it. [src: feature-tree.md §4.4a stated limit]
- [x] (P0, S) **CM-2 — a `pattern` of a cut whose replicated tools ALL clear the
      body was a SILENT NO-OP: the exact defect `fa30220` fixed for `mirror`
      only. Fixed 2026-07-25.** The reachability question is now ONE shared
      predicate (`geometry.kernel.removal.removal_reaches_body`, extracted from
      mirror's `_reflected_tools_reach_body` — topological, no epsilon); when no
      replicated tool reaches the body the pattern takes the whole-body ADD path,
      and one copy reaching anywhere keeps the cut path byte-identical. Measured:
      pocket source 14400.0 -> **28800.0**, hole source 15497.3452 ->
      **30994.6904**. `xfail` removed from
      `test_cm2_pattern_of_a_clearing_translation_is_not_a_silent_no_op`; 3 new
      guards in `test_pattern.py`. [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P1, S) **CM-3 — an `extrude-cut`/`revolve-cut` that removes nothing
      reported `ok` and returned the input body. Fixed 2026-07-25.**
      `combine_body` now asks the shared `removal_reaches_body` predicate BEFORE
      the boolean ("removed nothing" is invisible afterwards) and raises
      `CutRemovedNothingError` -> typed **`cut_removed_nothing`** on both cut
      funnels; Hole keeps `hole_off_body`/`hole_too_deep` through one `_cut_drill`
      adapter. The matrix's `extrude_cut` diagonal joins the self-composition
      ERROR class, so no verb is exempt any more. Cost: the worst cut-heavy tree
      147.0 -> 205.0 ms vs a 2000 ms ceiling. `xfail` removed from
      `test_cm3_a_cut_that_removes_nothing_must_error`; 3 new guards in
      `test_extrude.py` incl. the 0.25 mm^3 grazing-cut boundary.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P3, XS) **Friendly copy for `cut_removed_nothing`. Done 2026-07-25.**
      Keyed PER VERB in `FEATURE_SPECIFIC_ERROR` (FINDINGS #13 pattern) so an
      extrude-cut names the everyday cause — the same pocket cut twice — while
      revolve/sweep/loft name their own geometry; generic fallback added too.
      Covered in the jsdom tier (`FeatureTreePanel.test.tsx`) + unit lookups.
      [src: CM-3 fix 2026-07-25]
- [x] (P2, S) **CM-4 — a composed body loses STEP round-trip topology
      fidelity.** `plate 40x40x10 -> pocket -> fillet r3 -> shell t2` re-imported
      with faces 36 == 36 but **edges 96 -> 98**. FIXED 2026-07-25: the write is
      faithful (96 `EDGE_CURVE` records for 96 edges) — the shell returned a
      `BRepCheck`-INVALID body (outer wall and pocket wall offset onto the SAME
      plane, cavity pinched to zero width, leaving a T-junction), and the STEP
      reader was healing it on import. New `geometry.kernel.healing.conform_solid`
      (`ShapeFix_Shape`, only on a body `BRepCheck` already rejects, so valid
      bodies keep the identity path) conforms each shelled lump: dV -2.7e-12,
      dA 0.0, deterministic + idempotent, round-trip then EXACT (36/97/64).
      Marker removed from `test_cm4_pocket_fillet_shell_survives_a_step_roundtrip`;
      + `services/geometry/tests/test_healing.py` (5 guards).
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [ ] (P3, S) **`draft` propagates along a tangent chain with no UI/doc warning.**
      After an r4 corner fillet makes all four walls tangent-continuous, drafting
      the ONE picked +X face tapers all four walls plus the four fillet cylinders
      (1361.7627 mm³ removed vs 314.9581 for the named face). OCCT-correct
      (`BRepOffsetAPI_DraftAngle` propagates through tangent continuity) and
      usually desirable, but a picked-face UI never says so — doc + editor copy.
      Pinned by `test_observed_limit_draft_propagates_along_a_tangent_chain`.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]
- [x] (P0, M) **Composition-matrix gate — close the structural blind spot that
      let all five silent-wrong-geometry defects through. Shipped 2026-07-25**
      (founder directive: geometry correctness is the single thing capping this
      product). Every one of this week's five defects was a COMPOSITION of two
      features that each passed its own golden, because the golden inventory
      exercises verbs in ISOLATION.
      `services/geometry/tests/test_composition_matrix.py` composes 8
      predecessors x 13 composers (96 asserted cells; the diagonal is skipped
      with a reason and covered by re-issued-id self-composition tests) plus
      triples, asserting analytic volume where derivable and shape-independent
      invariants elsewhere (cut never increases volume; a clearing mirror is
      EXACTLY 2V; a patterned cut removes Nx the seed; removing nothing must
      error; suppress/unsuppress and edit/revert byte-identical; a same-face
      reference keeps its plane origin across a sibling edit; STEP round-trip of
      composed bodies). All five audited defects are seeded cases that fail on
      the pre-fix behaviour. 198 tests, 24-38 s — no nightly tier needed. Caught
      4 new live defects (CM-1..CM-4 above) + 2 locked observations. Tolerances
      are the two existing reviewed golden tiers (1e-9 planar / 1e-8 curved);
      none loosened. See `docs/GEOMETRY-QA.md` 2026-07-25.
      [src: founder directive 2026-07-25]
- [x] (P1, S) **Component-test tier (jsdom) — close the structural blind spot
      the production-readiness assessment surfaced. Shipped 2026-07-25**
      (founder directive). `apps/web` had NO DOM harness, so every defect that
      is "does this component render the value/copy it was given" was invisible
      below a 40-min Playwright run — which is exactly how the burn-down's dead
      `ExtrudePreviewState.operation`, hardcoded `mm³` assembly labels, and
      unkept focus-restore docstring all shipped. Both TS packages now run two
      vitest projects keyed on the file extension (`*.test.ts` → node,
      `*.test.tsx` → jsdom + Testing Library, shared `src/test/domSetup.ts`);
      no CI workflow change needed. 46 tests, each verified to fail against the
      re-introduced defect; the r3f-only extrude-ghost shading was extracted to
      a pure `extrudeGhostAppearance` seam instead of mocking three.js. See
      Changelog + ROADMAP.
- [x] (P0, M) Assembly STEP export — AP214 product structure. **Shipped
      2026-07-23** — `POST /api/v1/assembly/export` (geometry) + gateway proxy;
      `ExportAssemblyRequest` reuses `EvaluateAssemblyRequest` + format;
      `solve_assembly` extracted from `evaluate_assembly` (shared solve → placed
      kernel bodies) → `assembly/export.py` composes via build123d's XCAF writer
      (each instance a named PRODUCT at its solved world placement; STL bakes
      placements into one compound). Byte-deterministic (pinned timestamp +
      canonicalised NAUO occurrence ids); worked export→re-import→placement
      round-trip + PRODUCT-name traceability + no-body 422 over the bolted
      goldens. See Done archive.
- [x] (P1, M) **E1a — Section views END-TO-END wire (make the shipped kernel op a
      real capability). Shipped 2026-07-23.** Reshaped the geometry evaluate +
      compose wire so `section_params` is PER-VIEW — replaced the single
      request-level field with a map keyed by the section view's INDEX into `views`
      (`EvaluateDrawingViewsRequest.section_params: dict[int, SectionViewParams]`,
      `py_kit/schemas/drawings.py`), fixing the level mismatch and making >1 section
      view representable; a non-section request carries an empty map and composes
      byte-identically. geometry now consumes each section view's own params
      (`drawings/evaluate.py`), and the gateway `_compose_request` threads each
      persisted `ViewResponse.section_params` into that map (`grep section
      services/gateway/src/gateway/drawings.py` → 9 hits, was 0). Guards: a geometry
      end-to-end test composes a stored section (multi-view sheet: front + section)
      to a REAL hatched-section SVG — not `section_params_missing` — with a contrast
      test proving the empty-map path is the dead capability E1 replaced
      (`test_drawings_section.py`); the gateway half asserts `_compose_request`
      threads the persisted per-view params (`test_drawing_export_proxy.py`). Existing
      section/compose goldens byte-stable; contracts + ts-client regenerated.
- [x] (P2, S) **E1b — Section-view web authoring surface (apps/web). Shipped
      2026-07-23** — section views now FULLY end-to-end (kernel + wire + web
      authoring). New `SectionAuthorPanel` (a `drawing-section` command-band
      action + `S` shortcut, hung from the band like the sketch strip's offset
      panel): pick the cutting plane + which half is removed, then "Cut section"
      persists a `section` view carrying its `section_params`. The plane REUSES
      the sketch plane picker's exact vocabulary — the three origin datums OR an
      in-tree datum `FeatureRef` (new `resolveDatumPlaneOptions` in `sketch/
      plane.ts`, the ONE derivation the sketcher reads too; no parallel plane
      taxonomy, DRY). The v1 axis-aligned precondition is pre-checked client-side
      (disables Cut with a reason) and the server's `section_plane_not_principal`
      / `_misses_body` / `_empty` now render as readable failed-view guidance.
      `DrawingSheet` gains the on-screen `drawing-hatch` fill (new `drawing.hatch`
      token matching the server `_HATCH_INK` — one palette, two renderers), so the
      section hatches on-screen exactly as it exports. e2e authors a section on an
      XY+5 datum in the UI → hatched section (`section-view.spec.ts`); founder
      shots `drawings-section-{before,author,after}-*`. [src: AUDIT-ENGINEERING.md E1]
- [x] (P1, M) Assembly interference/collision detection. **Shipped 2026-07-23**
      — `POST /api/v1/assembly/interference` (geometry) + auth'd/rate-limited
      gateway proxy; reuses `EvaluateAssemblyRequest` input + new
      `InterferenceResult`/`ClashPair` DTOs. `solve_assembly` (shared solve →
      placed kernel bodies) + `kernel/interference.intersection_volume`
      (`BRepAlgoAPI_Common` via build123d, GProp volume) scanned pairwise
      (`assembly/interference.py`). Volume floor = one kernel-tolerance cube
      (1e-12 mm³) so a coincident-face touch is NOT a clash. N² over bodied
      instances documented as the accepted v1 bound (AABB broad-phase = v2).
      See Done archive.
- [x] (P1, S) Interference detector — close the silent false-negative on a
      boolean robustness failure (code-review 🟡, `e46db16`). **Shipped
      2026-07-23** — `kernel/interference` no longer `except Exception: return
      0.0`: on a `BRepAlgoAPI_Common` failure it now runs a robust solved-world
      AABB-overlap fallback (`probe_overlap` → `OverlapProbe` tri-state). Disjoint
      AABBs stay no-clash (a real interference is geometrically impossible);
      overlapping AABBs surface the pair as `ClashPair.unresolved=true` (new
      additive field) with the AABB-overlap magnitude hint — never hidden as clear
      (the dangerous FN for a collision check). Warning logged with both instance
      ids on the exception path. Guard tests force the boolean to raise for an
      overlapping- and a disjoint-AABB pair; existing 12 interference tests
      unchanged. Contracts + ts-client regenerated (backward-compatible — the web
      clash panel still renders `overlap_volume_mm3`). [src: AUDIT-ENGINEERING.md
      interference review]
- [x] (P3, S) Surface the `unresolved` clash state in the web clash panel.
      **Shipped 2026-07-25** — an unmeasurable pair reads as UNVERIFIED (dashed
      left rule + dashed stamp, gauge ink, magnitude parenthesised as a reference
      upper bound + "at most" caption) with a plain-language footnote; measured
      rows sort first and the eyebrow counts the states apart
      (`Interference · 1 · 1 unverified`), so an unverified-only report can never
      read as clear. Tree badge follows (UNVERIFIED, not the red CLASH claim);
      viewport still tints both. SAME commit fixed the audit residual: the clash
      volume now converts through the shared units core (`in³` on an inch
      assembly — it was the last mm-only readout on the page). New pure
      `assembly/clash.ts` + `clash.test.ts` + `AssemblyClashPanel.test.tsx` (dom
      tier) + e2e `assembly-clash-unverified.spec.ts`.
      [src: interference hardening follow-up 2026-07-23]
- [x] (P1, M) Assembly STEP import with product structure. **DONE 2026-07-23
      (slices 1+2a+2b) — assembly interop is now BIDIRECTIONAL; the "assembly is
      a one-way street" is closed.** Read AP214
      PRODUCT/NEXT_ASSEMBLY_USAGE_OCCURRENCE into positioned, NAMED Loft
      assembly instances — not one anonymous multi-lump body (today's MB-4b
      behavior). Acceptance: importing a multi-part assembly STEP creates an
      `assembly` document with N instances, each at the placement the STEP
      encodes (matched to tolerance) and named from its PRODUCT entity when
      present; a STEP with NO assembly structure still falls back to today's
      MB-4b single-body import (backward compatible); worked test against a
      real multi-part STEP fixture. [src: AUDIT-PRODUCT.md 2026-07-23]
      **SLICE 1 (geometry XCAF reader) shipped 2026-07-23**:
      `POST /api/v1/assembly/import` + `kernel/step_assembly.py` (XDE
      `STEPCAFControl_Reader` walk, the mirror of the export composer) →
      `StepAssemblyImportResult{has_assembly_structure, products[{name,
      placement, mesh_glb_id, properties}]}`; export↔import round-trip proves
      N products + placements (world centroid/vol within `roundtrip_tol`) +
      PRODUCT names recovered, incl. off-axis rotation + repeated part;
      flat/single-body STEP → `has_assembly_structure=false` (MB-4b path
      intact). **SLICE 2a shipped 2026-07-23 (reader hardened + editable body)**:
      the DoS parse-bound is now WIRED to the XCAF reader — the untrusted
      `ReadFile`/`Transfer` + product-tree walk run in the SAME killable
      subprocess (CPU-time `RLIMIT_CPU` + wall-clock backstop) the single-body
      reader uses, surfacing `import_parse_timeout` (422); the post-transfer
      walk/tessellate/measure/export phase is guarded so a transferable-but-
      degenerate solid is a typed 422, never a raw 500; each `ImportedProduct`
      now carries `body_step` (the LOCAL-frame, placement-stripped STEP fragment
      the single-body `import` feature ingests verbatim) + `body_step_id`
      (content-address dedup key — repeated part → one stored B-rep, N instances).
      **SLICE 2b SHIPPED 2026-07-23 (backend-builder):** documents
      `POST /api/v1/step-import` turns a `StepAssemblyImportResult` into a REAL
      graph — an `assembly` doc with one part per unique `body_step_id` (deduped)
      seeded with `ImportParamsV1(data=body_step)` (ZERO new ingest path) + one
      named instance per product at its placement (repeated part → ONE part / TWO
      instances), or (`has_assembly_structure=false`) the single-body MB-4b
      fallback; created ATOMICALLY (a rejected import leaves no orphan docs).
      Gateway `POST /api/v1/assemblies/import` is the first untrusted-upload
      entry: auth + rate-limited, a streamed byte-size cap BEFORE forwarding, an
      identity-free geometry hop, and a product-count cap
      (`MAX_IMPORT_ASSEMBLY_PRODUCTS=500`) enforced on the read BEFORE documents
      (bounds the post-transfer fan-out a small STEP could encode — slice-2a
      security review). New py-kit DTOs `ImportAssemblyRequest` /
      `StepImportResponse` (`AssemblyImportResult` | `SingleBodyImportResult`);
      contracts + ts-client regenerated. The true STEP-bytes round-trip
      (`export_step_assembly_bytes` → reader → documents) is a geometry/e2e gate.
      **AMPLIFICATION-DoS CLOSED 2026-07-23 (kernel-architect):** the untrusted
      parse's OUTPUT is now bounded AT THE GEOMETRY SOURCE, not only by the
      gateway's post-buffer count cap. An occurrence-count cap aborts the XDE walk
      inside the CPU-bounded child once leaf occurrences exceed
      `MAX_IMPORT_ASSEMBLY_PRODUCTS` (`import_too_many_products`, 422); a
      total-`body_step`-byte cap (`MAX_IMPORT_RESPONSE_BYTES` = 2x
      `MAX_INLINE_STEP_CHARS` = 32 MiB) rejects one large body instanced many
      times before the response is materialised past the ceiling
      (`import_response_too_large`, 422). Both typed, never a buffered multi-GB
      response or a 500.
- [x] (P2, S) Assembly import: carry `body_step` ONCE per `body_step_id`
      (transport efficiency + defense-in-depth). Today `StepAssemblyImportResult`
      repeats the full `body_step` text on every `ImportedProduct`, so a part
      instanced N times ships its B-rep fragment N times; the
      `MAX_IMPORT_RESPONSE_BYTES` byte cap makes the current shape SAFE, but a
      reshape (a shared `bodies: {body_step_id -> body_step}` map + products
      referencing by id) removes the amplification at the source and shrinks the
      transport. Cross-service DTO change (py-kit + geometry emit + documents
      consume + gateway forward + contracts/ts-client regen) — hence P2, not
      folded into the byte-cap slice. [src: slice-2b security review 2026-07-23]
      **SHIPPED 2026-07-25 (backend-builder):** `StepAssemblyImportResult.bodies`
      ({address -> fragment}) + `body_step_for()` as the ONE resolver; geometry's
      emit needed no change (the per-product field is hoisted, never serialized).
- [x] (P2, S) Assembly import: permanent 3-service HTTP integration test. The
      shipped unit suites cover geometry-read and documents-creation in ISOLATION
      but never the real gateway → geometry → documents HTTP chain. Port the
      qa-tester's full-chain harness (`scratchpad/assembly_import_roundtrip.py`)
      to a permanent, marked integration test so the untrusted-upload path
      (auth + byte cap + occurrence/response caps + atomic doc creation) is
      exercised end-to-end in CI/e2e, not just the two halves. [src: slice-2b
      security review 2026-07-23]
      **SHIPPED 2026-07-25 (backend-builder):**
      `gateway/tests/test_assembly_import_chain.py` — 3 apps in-process over
      `ASGITransport` (hermetic, ~14 s, `integration`-marked, DEFAULT pytest run).
- [ ] (P2, M) Drawings parity #4 — assembly drawing views + BOM/balloons (WIRE).
      The real capability behind the D4 gate: compose a drawing view that
      projects an ASSEMBLY (not a single part) — an assembly-side
      evaluation-request / compose branch, plus BOM table + balloon
      authoring/compose. The `assembly_views_unsupported` gate in
      `gateway/drawings.py` is REMOVED (slice 2). Supervised M feature (kernel +
      gateway + documents + web). [src: AUDIT-ENGINEERING.md D4 follow-on]
    - [x] SLICE 1 (geometry projection core): `evaluate_assembly_drawing_views`
          (`geometry/drawings/assembly_project.py`) — `solve_assembly` (reused
          verbatim) → `place_body` each instance at its solved world pose →
          compose ONE `Compound` → the SAME exact HLR `project_view` per view.
          Sibling DTOs `EvaluateAssemblyDrawingViewsRequest`/`Result` (reuse
          `EvaluateAssemblyRequest` verbatim; new `InstanceEvaluationError`) +
          route `POST /drawing/assembly/evaluate`; `just gen` regenerated.
          Golden `test_drawings_assembly_project`: 2-cube assembly front = 4
          visible + 4 HIDDEN (occlusion), top/right = 8 visible union; rotated
          instance silhouette; single-instance == part (byte-identical); typed
          degradation (bodyless instance / all-bodyless / unsupported view kind);
          determinism. [done 2026-07-23]
    - [x] SLICE 2 (gateway gate-removal + documents resolution): the
          `assembly_views_unsupported` fast-reject is GONE from both compose
          paths (`_aggregate_compose_request`); documents serves
          `GET /assemblies/{id}/evaluation-request`
          (`build_evaluate_assembly_request` — reuses `ordered_instances`/
          `ordered_mates` + the extracted shared `features.evaluation_prefix`);
          the gateway threads the resolved `EvaluateAssemblyRequest` as the new
          additive `ComposeDrawingRequest.assembly` (None = part compose,
          byte-identical). Single-level assemblies fully resolve; nested
          sub-assembly instances → empty prefix (typed `no_body`), flatten
          deferred. Contracts + ts-client regenerated. [done 2026-07-24]
    - [x] (a) **geometry compose branch — SHIPPED 2026-07-24**: compose routes
          branch on `request.assembly` → `evaluate_assembly_drawing_views` →
          mapped into the `EvaluateDrawingViewsResult` `place_sheet` consumes
          (`assembly_error`→`part_error`, dimensions empty — assembly-view dims
          out of v1). Assembly views now compose REAL silhouettes (visible +
          hidden-dashed) END-TO-END at the API; part compose (`assembly=None`)
          byte-identical; 6 new compose gates green; DE-4 cache key already
          hashes the whole request. (Reconciled by the orchestrator after the
          builder was killed by the session usage limit mid-regression-run —
          work re-verified green: drawings regression suites 100%, format +
          contracts regen completed, gen-check + web typecheck clean.)
    - [x] (b1) **BOM data model — SHIPPED 2026-07-25** (backend-builder):
          `GET /drawings/{id}/bom[?sheet=]` (documents read model + gateway proxy,
          `DrawingBomLine`/`DrawingBomResponse` extending the shipped `BomLine`).
          **Item numbers are DERIVED, never stored** (design §8a.1): numbered by
          first appearance in the assembly's `order_index`, so a part RENAME can
          never renumber a print (the name-sorted `/assemblies/{id}/bom` order is
          deliberately different, gated). Staleness is visible not silent —
          `assembly_version` echoed (tip-tracking, §8a.2) — and every failure is
          typed: `drawing_bom_source_not_assembly` / `sheet_has_no_views` /
          `drawing_bom_source_missing` 422, `sheet_not_found` 404, a dangling
          reference keeping its number + quantity with `missing: true`. 15
          documents regressions x2 dialects + 4 gateway proxy gates; contracts +
          ts-client regenerated.
    - [ ] NEXT SLICES (scoped):
          (b2) **BALLOONS — one whole slice, kernel + backend + web together**
          (splitting it would persist balloons no serializer draws = a dead
          capability). Decisions already made in drawings.md §8a.3: a balloon
          stores the BOM line KEY (`ref_document_id`+kind) + its authored 2D
          leader/anchor and NEVER the number (resolved from (b1) at compose time);
          a balloon whose document is no longer instanced is a typed
          `balloon_item_missing` dangling marker, never a stale number. Work:
          promote the `Annotation` alias to a `type`-discriminated union with a
          `balloon` member (documents persists it through the SHIPPED annotation
          table — no migration); add `ComposedBomTable` + `ComposedBalloon` to
          `ComposedSheet` and place them in geometry `place_sheet` (thread the
          resolved BOM through `ComposeDrawingRequest`, additive/null = today's
          byte-identical sheet); all three serializers render them; web authors the
          balloon + renders the table. Gates: a compose golden with 2 items + 2
          balloons, byte-identical no-balloon sheet, `balloon_item_missing` gate.
          (c) web — render assembly views (web reads the SAME `/drawings/{id}/sheet`
          `ComposedSheet`, so (a) alone lights the on-screen sheet up); (d) documents
          — nested sub-assembly FLATTEN (recursive instance walk composing
          placements; today a nested instance degrades to typed `no_body`), which
          also unlocks the recursive/indented BOM.
- [x] (P2, S) Dedicated Hole feature — SLICE 1 (simple hole): `HoleFeature`/
      `HoleParamsV1` registered across ALL feature-registry arms (Feature union,
      FeatureEnvelope, FEATURE_REGISTRY, BODY_AFFECTING_FEATURE_TYPES,
      feature_references, evaluate handler + dispatch + _BODY_AFFECTING_TYPES);
      face-based placement (a planar-face `SubshapeRef` — the SAME grammar the
      on_face datum uses — + a world point projected onto the face) with
      diameter + through-all|blind depth; auto correct cut direction (into the
      solid, opposite the face normal). Golden `hole-through-r5-40x25x10`:
      analytic volume parity (block − π·r²·h) AND parity vs a hand-built
      sketch+extrude-cut (identical volume/area/topology/mesh). Typed
      degradation: `hole_off_body` / `hole_too_deep` / `subshape_unresolved` /
      `no_prior_body` (never-500). documents picks it up centrally (shared
      registry). [done 2026-07-23]
- [x] (P2, S) Dedicated Hole feature — SLICE 1 WEB authoring: a Hole command
      (band action in Modify + `O` shortcut) hangs a `HoleEditor` like the
      extrude/section editors — pick a face (REUSES `FacePickOverlay`, the SAME
      stage-1 signature the on_face datum / sketch-on-face flows echo), pick a
      point ON it (`HolePointOverlay` — the measure overlay's DOM-in-canvas
      `PickNode`, offering the face centre + its coplanar corner snaps; a face
      pick seeds the point to the centroid so the form is immediately valid), set
      Ø + through-all|blind depth, drill via the shared feature-create path. Typed
      rebuild errors (`hole_off_body`/`hole_too_deep`/`subshape_unresolved`/
      `no_prior_body`) read as guidance through `friendlyFeatureError`. e2e drills
      a through-all + a blind hole in the UI on the real isolated stack (feature
      lands + body re-renders + reload holds); 13 `hole.test.ts` units; founder
      shots (1440 + 1280×800). [done 2026-07-23]
- [x] (P2, S) Dedicated Hole feature — SLICE 2 GEOMETRY CORE (counterbore +
      countersink): additive `HoleType`-discriminated member on `HoleParamsV1`
      (`simple` default = byte-identical slice-1, no `param_version` bump — the
      RevolveAxis/DatumParams idiom); kernel `cut_counterbore` (larger coaxial
      cylinder) + `cut_countersink` (coaxial cone from mouth Ø to bore Ø at the
      included angle), coaxial with the bore via the shared face-normal axis.
      Goldens `hole-counterbore-d18-r5-40x25x10` (analytic π·r²·H+π·(R²-r²)·h,
      cross-checked vs a 2-step extrude-cut) + `hole-countersink-d18-90deg-...`
      (analytic frustum); typed degradation `hole_cbore_invalid` /
      `hole_csink_invalid` / `hole_too_deep` (never-500). gen-check + apps/web
      typecheck clean (no other schema perturbed). [done 2026-07-23]
- [x] (P2, S) Dedicated Hole feature — SLICE 2 WEB authoring (counterbore +
      countersink): the `HoleEditor` grows a quiet `Type` SegmentedControl
      (Simple | C'bore | C'sink) revealing the recess fields — counterbore
      {`cbore_diameter_mm`,`cbore_depth_mm`}, countersink {`csink_diameter_mm`,
      `csink_angle_deg` with 82°/90° fastener-standard preset chips}. The
      "recess Ø must exceed bore Ø" precondition is guarded client-side (inline
      field error + disabled Create); typed rebuild errors `hole_cbore_invalid` /
      `hole_csink_invalid` humanised via `friendlyFeatureError`. Simple omits
      `type` on the wire (byte-identical slice-1 — backward-compatible edit). e2e
      drills a counterbore AND a countersink in the UI on the real stack (Solved +
      recessed body); +11 `hole.test.ts` units; founder cbore/csink authoring +
      result shots. Hole slice 2 is now END-TO-END in-app. [done 2026-07-23]
- [ ] (P2, S) Dedicated Hole feature — SLICE 2 TAIL: tapped hole type; standard
      drill-size tables (+ a follow-up MCP/scripting exposure). Seeds Drawings
      hole callouts. [src: AUDIT-PRODUCT.md 2026-07-23]
      - [x] Tapped geometry + DTO (2026-07-25, kernel-architect). v1 threads are
            **COSMETIC** (decision + trade-off + modelled-thread upgrade path in
            `geometry/kernel/threads.py`): the kernel cuts the ISO tap-drill bore
            `D - P` and carries a typed designation for drawing/BOM callouts — no
            helix, so a tapped hole costs 1 face, not hundreds. `thread:
            IsoMetricThread | None` is its OWN optional param, NOT a 4th `HoleType`
            member (threading is orthogonal to the recess → a counterbored tapped
            hole is one feature, and the `HoleType` union stays untouched). ISO 261
            table M1.6–M64 (coarse + fine); `hole_thread_unsupported` (unknown
            designation) / `hole_thread_mismatch` (bore outside `[minor, nominal)`)
            are validated BEFORE any geometry, so neither degrades to a plain hole
            wearing an uncuttable callout. Proof: golden
            `hole-tapped-m10x1.5-40x25x10` (analytic 9432.549826945344 = 10000 −
            180.625π; topology 7/15/1 — IDENTICAL to the untapped bore), the
            evaluate response is BYTE-identical to the same hole untapped, and
            matrix verb `hole_tapped` (+8 cells) proves pattern/mirror of a tapped
            hole array the BORE. gen-check clean (additive optional field).
      - [x] Web authoring (2026-07-25, frontend-builder). A `Tapped` CHECKBOX
            beside the Type control (not a 4th segment — threading is orthogonal
            to the recess) reveals a drafting thread note: brass callout stamp,
            ISO size + pitch pickers (coarse first), tap-drill preset chip.
            Picking a designation DERIVES `diameter_mm` to `D - P` without
            locking it (a shop's 6.8 for M8x1.25 still submits); both typed
            errors are guarded client-side and humanised via
            `friendlyFeatureError`. ISO 261 table mirrored in
            `features/thread.ts`, kept honest by a test that parses
            `geometry/kernel/threads.py`. The FEATURE TREE row carries the
            designation (`hole · M10x1.5`) — a tapped hole's solid is
            byte-identical to its bore, so the UI is the only place it exists.
            e2e (derive → mismatch guard → Solved → survives reload; + a tapped
            counterbore) + founder shots at 1440/1280. [done 2026-07-25]
      - [x] Drawing THREAD SCHEDULE (2026-07-31, kernel-architect) — BACKLOG #50,
            the output half. A tapped hole's solid is byte-identical to its bore, so
            the print is the only place the thread can exist; it reached none. Now a
            derived QTY / THREAD / TAP DRILL block (bottom-left, the corner the title
            block and bend table leave free) in SVG, PDF and DXF, rolled up per
            designation from the feature params at compose time — never stored, so a
            re-tapped hole cannot leave a stale callout. Asserted on the DOWNLOADED
            bytes incl. a route-level POST. NOT done, with reasons on
            `ComposedThreadSchedule`: a BOM column (a BOM line is a DOCUMENT; a part
            with four M6 + two M8 has no single thread value) and a STEP thread
            annotation (AP242 PMI, which OCCT does not write and AP214 cannot
            express).
      - [ ] Standard drill-size tables (+ MCP/scripting exposure). The tap drill is
            already served on the drawing's thread schedule; this is the wider stock-
            drill table + agent surface.
- [x] (P2, S) Feature suppress — mark a feature suppressed (persisted flag); tree
      rebuild skips it, downstream features rebuild off the last non-suppressed
      state (or typed-fail if they reference the suppressed feature directly). A
      daily incumbent verb, previously absent (`grep suppress` → empty).
      **FULLY END-TO-END 2026-07-23** (schema+evaluator kernel-architect;
      persistence+toggle backend-builder; web tree toggle frontend-builder):
      toggle in the feature tree; suppressing a fillet re-evaluates to the
      un-filleted body; un-suppressing restores it; worked e2e. [src:
      AUDIT-PRODUCT.md 2026-07-23]
      - [x] Slice 1 — schema + geometry evaluate. `suppressed: bool = False` on the
            shared `FeatureEnvelopeBase` (all 19 envelopes inherit; no param_version
            bump), `FeatureResult.status` gains `suppressed`, and `evaluate_tree`
            SKIPS suppressed features (downstream rebuilds off the last
            non-suppressed body) with a typed `references_suppressed` error for a
            feature that references a suppressed one. Proof: `[sketch,extrude,fillet]`
            fillet-suppressed → analytic box volume, un-suppressed → filleted;
            middle-suppress rebuilds downstream off the reduced body; ref-to-suppressed
            → 200 typed error (test_evaluate_tree.py). feature-tree.md §4.3a.
            2026-07-23 (kernel-architect).
      - [x] Slice 2a — documents persistence + toggle endpoint + gateway proxy.
            `features.suppressed` NOT NULL BOOLEAN column (migration `0009`,
            server-default false; `metadata.create_all` renders it for native/e2e).
            create/update store it (create no longer drops `suppressed:true`);
            `_to_response` + the `/evaluation-request` builder pass it back through
            `FEATURE_REGISTRY.load(..., suppressed=…)` (proof: a created-suppressed
            feature reaches geometry marked; test_evaluation_request.py). Dedicated
            `PATCH .../features/{id}/suppress` (py-kit `FeatureSuppressRequest`,
            body `{expected_tree_version, suppressed}`) flips ONLY the flag, bumps
            `tree_version` (stale → 422), records history (undoable); gateway proxy
            auth-gated. History serialize/apply carry `suppressed` so undo restores
            it. 2026-07-23 (backend-builder).
      - [x] Slice 2b — web tree suppress toggle + dimmed row. `suppressFeature`
            (consumes the generated `FeatureSuppressRequest`; stale 422 →
            refetch fresh tree_version + retry once) behind a per-row toggle in
            `FeatureTreePanel` (`aria-pressed` + accessible name +
            `data-suppressed`; new `SuppressIcon` primitive). A suppressed row
            reads QUIET — dimmed + struck-through name, `SUPP` status, brass
            pressed toggle — distinct from a red error. Proof
            (feature-suppress.spec.ts, real isolated stack): suppress a fillet in
            the tree → sharp 8,000 mm³ cube + dimmed/SUPP row + Solved (row
            stays, reversible); un-suppress → fillet returns. Founder shots
            feature-suppress-{before,on,off}-desktop + -on-laptop (1440 +
            1280×800). 2026-07-23 (frontend-builder).
- [x] (P2, S) Mirror feature — mirror a feature/body about a plane (origin/datum),
      one op in every incumbent. **END-TO-END 2026-07-23** (geometry+DTO
      kernel-architect; web authoring frontend-builder): `MirrorFeature`/
      `MirrorParamsV1` (plane = the SAME `GeomRef` a sketch uses — origin datum or
      `datum` feature) reflects the current body and unions the reflection into the
      chain (pattern-feature semantics; a disjoint reflection is a valid 2-lump
      body, not a `pattern_disjoint`). Golden `mirror-triangle-prism-2x` (analytic
      2V + centroid-on-plane reflection proof); typed degradation
      (`no_target_body` / `reference_unresolved` / `mirror_failed`). WEB: Modify-band
      Mirror command (shortcut I) + `MirrorEditor` in the shared editor seat,
      reusing the sketch/section plane picker (`resolveDatumPlaneOptions`);
      `mirror` added to frontend `BODY_AFFECTING_FEATURE_TYPES` + drift guard; e2e
      `mirror.spec.ts` mirrors a real body (Z-extent + volume double about XY).
      [src: AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P2, S) Drawings — PROCESS GUARD: a non-default-value compose golden per
      optional authored field. **Nearly closed** — title-block (D1), first-angle
      (D3), and dimension-placement (D2) goldens all landed this batch; only the
      D5 orientation (portrait) golden remains once D5 authoring ships. [src:
      AUDIT-ENGINEERING.md cross-cutting]
- [x] (P2, S) E2 — gateway `assembly/export` + `assembly/interference` web
      consumer. **CLOSED 2026-07-23** — web half landed: `exportAssembly` +
      `checkInterference` (`api/assemblies.ts`, generated client only) drive an
      assembly Export strip (STEP/STL via the shared `ExportRow`) and a third
      "Clash" inspector view — a ruled interference schedule (each pair's
      balloons + exact `overlap_volume_mm3`), an explicit "No interferences
      found" empty state, and clashing instances flagged red across DOM (tree
      `CLASH` badge) + WebGL (edge/surface + balloon, shared `assembly.clash`
      token). Command-band "Check interference" (shortcut I). e2e
      `assembly-inspect.spec.ts` (STEP download + populated/empty clash) green
      on the real stack. Proxy-test half landed earlier same day. [src:
      AUDIT-ENGINEERING.md E2 2026-07-23]
- [ ] (P2, S) Assembly export — persistent ROTATED multi-instance golden under
      `goldens-assembly/`. Both shipped export goldens
      (`assembly-two-plates-bolted`, `assembly-two-plates-gap`) solve every
      instance to IDENTITY orientation, so the `gp_Quaternion` placement path is
      only guarded by a synthetic test (`test_step_assembly_export_nonidentity_
      rotation_roundtrip`, added by geometry-QA 2026-07-23). Lock a 3-instance /
      repeated-part / non-identity-rotation assembly as a committed golden so the
      "green suite, wrong rotated geometry" hazard is a permanent gate, not a
      synthetic one. [src: GEOMETRY-QA.md 2026-07-23 assembly-export QA]
- [x] (P2, S) Revolve: construction-centerline axis opens the profile —
      SHIPPED 2026-07-23 (kernel-architect). A half-profile OPEN only along the
      axis (the on-axis edge is a `construction` centerline, excluded from the
      wire) now revolves about that centerline: `build_revolve_profile_face`
      first tries the SHARED `build_profile_face` (existing real-edge / offset-
      washer paths byte-identical), and on `profile_not_closed` retries with the
      axis line promoted to a real closing edge — closing exactly the face a real
      on-axis edge would give. A profile open somewhere OTHER than the axis stays
      `profile_not_closed` (over-acceptance guard test). New golden
      `revolve-centerline-cylinder-r12-h20` (analytic V=2880π, all gates +
      cross-process determinism + STEP round-trip green); revolve-annulus golden
      byte-identical. WEB FOLLOW-UP (not this commit): the revolve editor's axis
      picker should allow selecting a construction line as the axis (the sketcher
      already authors construction lines; verify the pick filter doesn't exclude
      them). [src: product-auditor]
- [x] (P2, S) Revolve construction-centerline axis — WEB end-to-end —
      SHIPPED 2026-07-23 (frontend-builder). Verified the axis picker already
      offers `construction: true` sketch lines (`axisOptions` ranks them FIRST,
      `defaultAxisId` selects the centerline) — NO filter fix needed; the
      capability was already reachable in-app. Added the regression guard: a
      Playwright e2e (`revolve-ui.spec.ts` "construction centerline closes a
      half-profile → solid cylinder") sketches the golden half-profile (open
      only along x=0, centerline ends snapped to the on-axis corners), picks the
      construction line as the axis, and asserts a solid cylinder r12/h20
      (V=2880π) lands Solved in the tree. Humanised the typed revolve rebuild
      errors (`no_axis`, `profile_not_closed`, `axis_intersects_profile`) in
      `featureErrors.ts` — `profile_not_closed` now names the snap-ends-to-open-
      corners requirement. Founder shots: `revolve-centerline-{sketch,body}-
      {1440,1280}.png`.
- [x] (P2, S) Datum editor: midplane FACE-sides + `on_face` authoring —
      SHIPPED 2026-07-23 (frontend-builder). The `FacePickOverlay` is wired into
      the standalone `DatumEditor`: an `on_face` kind and midplane FACE-sides
      each arm the SAME viewport face pick the sketch-on-face flow uses, and a
      clicked planar face folds into the slot as a full-precision `SubshapeRef`
      (reusing `faceSubshapeRef`/`onFaceDatumParams`, so the authored params —
      and the kernel-resolved basis — match sketch-on-face exactly). Editing an
      existing on_face / face-midplane datum re-seeds its picked face(s) from the
      stored signature. Worked e2e (`datum-face-pick.spec.ts`, 5 tests): each
      authored face-datum evaluates to "Solved" (kernel resolved the picked
      signature) and survives reload; Escape disarms an armed pick. Founder shots
      `datum-on-face-*` (1440 + 1280×800). [src: frontend-builder]
- [x] (P0, M) 2026-07-24 hard-audit P0 + tooltip P1 — command band measured
      tiers + z-layer scale. SHIPPED 2026-07-24 (frontend-builder): new
      `CommandBand` primitive measures the labeled row against its own width
      and steps labeled→icon (`data-band-tier`; ToolButton's stale ≥1360px
      arithmetic deleted); `overflow-x: clip` — the band can never widen the
      root or hide a group; `zLayer` tokens (overlay<panel<hud<band<menu)
      lift band tooltips above the floating panels. Guard
      `e2e/toolbar-overflow.spec.ts` (1280/1440/1600/2400: groups reachable,
      no root scroll, tier fits, tooltip z-order). Founder shots
      `toolbar-band-fix-{1440,1600}.png`,
      `toolbar-tooltip-above-panel-1440.png`. [src: UI-REVIEW 2026-07-24]
- [x] (P1, M) FINDINGS #8 live preview while editing — extrude ghost
      (`apps/web`, `packages/design`). The open extrude editor paints a
      translucent brass-edged ghost of the swept profile that tracks the
      distance/direction live, before Save; client-side
      (`viewport/profileLoops.ts` → `three.ExtrudeGeometry`, no kernel round-
      trip per keystroke), studio matcap + new `viewport.preview` tokens, GPU
      resources disposed on change/unmount. Datum/fillet previews = follow-ups.
      web unit 810 pass; e2e `interaction-depth.spec.ts` (ghost pre-Save +
      distance-live + laptop); shots `extrude-ghost-{desktop,laptop}.png`.
      [src: UI-REVIEW 2026-07-24 / FINDINGS #8]
- [x] (P1, M) FINDINGS #9 feature-localized selection (`apps/web`,
      `packages/design`). The GLB merge keeps one draw group per B-rep face
      (`mergeGeometries(parts, true)`; group ordinal == `OverlayFace.index`);
      the `/overlay` per-face `feature_id` maps a selected feature → its face
      set, which takes a deeper warm-brass matcap multiply
      (`viewport.featureSelect`) + brass boundary edges (`subsetEdges`) while the
      studio matcap is PRESERVED on the rest. Feature-select (proper subset) and
      whole-body select (a feature owning every face) are distinct states.
      Raster-independent QA hooks (`data-body-highlight`, `data-selected-faces`/
      `data-total-faces`); web unit 818 + design pass; e2e
      `feature-selection.spec.ts` green on the live stack; founder shots
      `finding9-{feature-localized,whole-body}-{desktop,laptop}.png`. [src:
      UI-REVIEW 2026-07-24 / FINDINGS #9]
- [x] (P1, M) FINDINGS #10 right-click context menus (`apps/web`,
      `packages/design`). One reusable token-styled `ContextMenu` primitive
      backs the viewport menu (fit / home / front·top·right·iso / new-sketch /
      sketch-on-face / measure / suppress·delete selected) + the feature-tree
      row menu (edit / inline rename / suppress / delete). Rename + delete use
      the generated client's name-PATCH + DELETE-feature routes (OCC + stale-
      retry, DRY); every row is a wired action. Keyboard-nav + focus-visible +
      reduced-motion. web unit 810 + design 42 pass; e2e view-snap + row
      rename/delete; shots `{viewport,tree}-context-menu-desktop.png`.
      [src: UI-REVIEW 2026-07-24 / FINDINGS #10]
- [x] (P2, M) 2026-07-24 hard-audit P2 — "registers read as templated web
      tables". SHIPPED 2026-07-25 (frontend-builder). One `DocumentRegister`
      replaces three near-duplicate pages. Columns now answer a modeler's
      questions: LAST WORKED (relative age; "Not started" when a document has
      had no edit since it was named) + UNITS where `length_unit` exists —
      replacing two columns of the same ISO date. Scribed sheet-number gutter
      with the addressed row's brass scribe; the create control is the
      register's next line (`N` chord shown); ruled unfiled lines run to the
      frame edge. `DocumentRegister.test.tsx` 13 + `activity.test.ts` 7; all
      test ids/roles kept; e2e parts-home/auth/drawings/assembly-bom green;
      `parts-home-*.png` refreshed. [src: UI-REVIEW 2026-07-24 P2]
- [x] (P1/P2, M) FINDINGS #6/#15/#21 drawings/HLR burn-down wave 3
      (`services/geometry`, `packages/py-kit` drawings schema). #6: non-overlapping
      sheet layout — `place_sheet` free-slots additive section/flat_pattern views
      clear of the standard quartet (was dead-centre collision) + honors authored
      positions when `SheetViewPlacement.auto_place=false` (new additive field, the
      drag-to-place seam). #15: `ComposedView.error` carries the typed per-view
      `FeatureError` through compose; SVG/PDF/DXF stamp the reason. #21:
      `_canonicalize` subtracts a visible line's collinear coverage from an
      overlapping hidden line so a partially-occluded segment is never double-emitted
      dashed+solid. Regressions: 5-view zero-overlap, honored-position, typed-error-
      preserved, partial-occlusion split. Goldens refreshed (additive `error` field);
      `just gen`/`gen-check` clean. [src: FINDINGS #6/#15/#21]
      Follow-up 2026-07-25: #21's ASSEMBLY-path guard was left `xfail(strict=False)`
      and had been XPASSing since this commit — marker removed, real assertion now.
- [x] (P1, S) FINDINGS #7 assembly STEP writes UUIDs as PRODUCT names
      (`services/geometry`, `services/documents`, `packages/py-kit`). New optional
      `EvaluatedInstance.name` threads the human-readable instance name (populated at
      the documents `build_evaluate_assembly_request` seam) → `PlacedInstance` → the
      STEP PRODUCT name (falls back to the id when absent); import already preferred
      the stored PRODUCT name, so a Loft→STEP→Loft round trip now recovers
      `Base Plate`/`Top Plate` not `c8f8baa9-…`, placements intact. Regression
      `test_step_assembly_export_preserves_human_readable_product_names_roundtrip` +
      documents seam assertion; additive ts-client, `gen-check` clean.
      [src: FINDINGS #7 / AUDIT-PRODUCT.md]

## Next (P2)

- [x] (P2, M) **QA3-3 — selecting a Ø3 hole lit the whole plate; a feature now owns
      the faces whose SURFACE it created. CLOSED 2026-08-01** (kernel-architect).
      `attribute_faces` credited a face to the earliest feature after which it
      existed in its FINAL form, so any cut re-bounding a large face took it: the
      remix's 5th hole owned 3 of 18 — its 75.4 mm² wall plus the vendor plate's
      1 323.8 mm² top and 1 682.7 mm² back. The rule is now geometric, not a size
      heuristic (an area cutoff would fit this plate and invert on the first small
      face drilled — gated by a 3×3×20 post whose 5.9 mm² drilled top is smaller
      than the 125.7 mm² wall of the same bore): each face resolves to the earliest
      snapshot that already had its supporting `SurfaceKey` — canonical plane /
      cylinder / cone / sphere / torus read off the exact B-rep — provided the final
      patch lies INSIDE that surface's extent then, since a plane is unbounded and
      two disjoint coplanar cubes would otherwise merge (6/6 → 10/2 on
      `multibody-two-disjoint-boxes` before the guard). NEMA remix now **1/17 of 18**
      (hole owns only its bore wall); block+hole 1/6 of 7; chamfer-plate 4/6 not
      10/0; shell-pinch 8+17 not 17+19; 28 of 47 feature-tree goldens change
      ownership, none change stored numbers (attribution is not a golden field).
      No contract change — a face still carries one `feature_id`. Cost: the surface
      key + extent add ~13.5 µs/face and the index is built by the RECORDER, so the
      interactive pass stays O(final faces) at 14/23/46 ms (tray N=25/50/100, was
      13/21/39 by PERF-5b) and recording goes 21/56/155 → 27/71/203 ms.
      New `test_provenance_surface.py` (11 gates, incl. monotonicity and free-form
      fallback). `import-remix.spec.ts` exact counts need 3→1 / 15→17 and 6→5 / 5→6
      (frontend territory; handed over, not edited here).
      [docs/QA-REVIEW.md 2026-08-01 QA3-3]

- [x] (P2, S) **GATE-1 — CI ran nothing that drove a browser, so a stale spec
      could sit red at HEAD for a day while every commit read green. CLOSED
      2026-08-01** (platform-builder). `.github/workflows/e2e.yml` runs the FULL
      Playwright suite on every push that touches code, sharded 4 ways
      (`scripts/e2e.sh --web-only -- --shard=i/4`; `just e2e-web` reproduces a
      red shard locally). The choice was argued from cost and coverage, not
      preferred: **PR-only** would never have run (we push straight to
      `claude/**` and open no PRs); **nightly-only** attributes a failure to ~20
      commits up to 24 h later, which IS the defect being closed; a **write-path
      subset** is a hand-maintained list — the "enumerated gate quietly stops
      covering" class this repo has now hit four times — and would not have
      caught this bug either, since `interaction-depth.spec.ts` is a
      right-click/ghost-preview spec no honest subset would list. Sharding is
      derived from the FILESYSTEM, so a spec added tomorrow is gated the day it
      lands. Wall clock ~8-15 min per push (352 tests / 81 files; ~30 min serial
      quiet, ~60 min under four-agent load), i.e. at or under ci.yml's `python`
      job, so feedback latency does not regress; ~45-75 runner-min per code push.
      A `reconcile` job re-derives the expected set with `playwright test --list`
      and fails unless the shards executed it exactly once between them
      (`scripts/e2e-shard-audit.py`, proven against three negative controls:
      a spec no shard ran, a spec two shards ran, a missing shard report).
      **NOT covered per push, named so nobody assumes otherwise:** markdown-only
      commits (30 % of the last 100 — `paths-ignore`, so no e2e run exists for
      that SHA at all; `git show --name-only` distinguishes it from an eviction),
      the browser against Postgres (this gate uses the native SQLite boot —
      `deploy-path.yml` drives the real Postgres/MinIO round-trip per push), and
      non-Chromium browsers (the config declares only Chromium). One disclosed
      compromise: the gate runs `--retries=1`, because the measurement found a
      racy spec (GATE-1a) and a gate people learn to re-run is worse than no
      gate — a deterministic defect still fails both attempts, and a retried
      test is NAMED as a warning every run rather than swallowed.
      Acceptance met by deliberate failure, not assertion: the exact stale
      assertion from `60a9553` was re-introduced, pushed, and CI rejected it —
      run ids in the batch report, with `ci.yml` GREEN on the same commit, which
      is the whole point.
      **The first attempt at that proof FAILED, and the failure is the useful
      part.** All three pushed runs came back red — including the two that
      should have been green — because Vite never answered inside the 60 s
      `webServer.timeout`: Vite forces `dns.setDefaultResultOrder("verbatim")`,
      so on a DUAL-STACK host its default `localhost` binds `::1` while
      `baseURL` asks for `127.0.0.1`; the process stays alive and never
      answers ("Timed out", not "exited early"). Unreproducible here — the dev
      container has no IPv6 loopback at all, which is exactly why it survived
      every local run. The red negative-control commit was therefore red for
      the WRONG reason and proved nothing, which is the same defect this repo
      keeps closing: a gate asserting something it does not know. Fixed by
      binding the literal IPv4 loopback (`pnpm dev --host 127.0.0.1`), piping
      the webServer's output so a failure names its cause instead of timing out
      silently, and a CI preflight in `scripts/e2e.sh` that serves the app on an
      isolated port and PRINTS which address answered — so if the diagnosis is
      ever wrong again, the log says so in one line rather than costing a round
      trip.
      [src: batch-end e2e 2026-08-01]
- [x] (P2, XS) **GATE-1a — the browser gate no longer needs `--retries=1`.
      SHIPPED 2026-08-01** (frontend-builder). `--retries=1` is out of
      `.github/workflows/e2e.yml` and `--fail-on-flaky` is passed to the reconcile
      audit, so a retried pass is a red build again. The fix is the rig's own
      signal rather than the suggested poll-the-width (which would have retried
      the assertion but still guessed at the settle): the spec blanks
      `data-fit-rect` and waits for `CameraRig`'s `onSettle` to write a fresh one,
      so it returns as soon as the move lands and cannot pass early. Measured
      both ways under four CPU burners on 4 cores (load avg ~8): the OLD shape
      failed **1/10** repeats, the new one passed **10/10** in the same window —
      the negative control matters, since "10/10 under load" is worthless if the
      load was too light to expose the race. Suite audit: 17 `waitForTimeout`s,
      4 gating a non-retrying assertion — `viewport-gestures`' raster compare is
      now an `expect.poll`; `part-visibility` / `assembly-visibility` sample
      after real PAINTS (`support.ts waitForFrames`, rAF ticks, which stop when
      the browser stops drawing) instead of 400/450 ms of wall clock. The other
      13 are screenshot settles or absence assertions, where a sleep is correct;
      `viewport-makeover:373` is named explicitly — it sleeps to prove the camera
      did NOT move, so a slow box can only make it pass, never fail. 30 specs
      re-run green under the same load. Residual, filed rather than hidden: the
      `--fail-on-flaky` help text in `scripts/e2e-shard-audit.py` still says the
      flag is "off while the known racy specs are being hardened" (platform
      territory, one line). The shape this closes, for whoever hits it next: a
      fixed sleep is only ever safe before a LOCATOR assertion, which retries
      itself; before a numeric one it IS the gate, and it has to be right every
      time on a machine you do not control. [src: GATE-1 full-suite measurement
      2026-08-01]
- [x] (P2, S) **PERF-1c — the prefetch headline is the BEST case, and we do not
      know the typical one** (kernel + QA). PERF-1b's table is measured with the
      warm run to COMPLETION: the 7.0x commit / 7.9x pick at N=200 `#192` assume
      the user sat in the editor for the full 28.9 CPU s the warm costs. A real
      edit is "open extrude, type 12, Enter" — 3-5 s. Since warming follows the
      same `N^1.85` curve, a few seconds of dwell reaches only a short prefix and
      removes a correspondingly small share of the rebuild (rough estimate, NOT
      measured: ~5 s of dwell at N=200 removes on the order of 15 %, i.e. 34 s ->
      ~28 s, not -> 4.8 s). Nothing is wasted — a partial prefix is a legitimate
      resume point and the work is the commit's own, moved earlier — but the
      number we publish should be the one a user gets.
      Acceptance: measure warm-completion-vs-dwell at 2 s / 5 s / 15 s for N=50 /
      100 / 200, publish the EXPECTED win beside the ceiling in `docs/PERF.md`,
      and state which part sizes benefit at realistic dwell. Then decide, with
      the data, whether the trigger should fire EARLIER than editor-open — e.g.
      on feature-row selection, which precedes the dialog by a beat — and whether
      the 30 s budget is still the right split once the commit lineage is known
      to be the only one most dwells can reach.
      Founder question that prompted this: "is this the numbers users are
      experiencing or just what happens under the hood without them noticing?" —
      a fair challenge to a table that answered a different question than it
      appeared to. [src: founder 2026-08-01 · docs/PERF.md 2026-08-01]
      **ANSWERED 2026-08-01** (kernel): the win is a STEP at the warm's own
      completion (~0.85x the cold rebuild per lineage), not a ramp, because a
      partial prefix cannot help a request that already probed the cache.
      Expected commit win by dwell — N=50: 1.0x / **7.0x** / 7.5x at 2 / 5 / 15 s;
      N=100: 1.0x / 1.0x / **16x**; N=200: 1.0x at every dwell a human produces
      (its ceiling of 18.8x needs D >= 30 s). So the prefetch is worth 7x on a
      50-feature part at a realistic 3-5 s edit and NOTHING at 200. The trigger
      did not move: it already fires on feature-row selection (the same event
      that opens the editor), and the deficit at N>=100 is seconds-to-tens-of-
      seconds, which no trigger nudge closes. No dwell timer either — the
      pessimisation was contention, not earliness, and a start delay would push
      the step further out. [docs/PERF.md 2026-08-01b]
- [ ] (P2, M) **PERF-6 — prefetch the prefix an open editor has already
      declared stable** (kernel + frontend). BLOCKED ON PERF-1: with no cache,
      prefetching does the same 27 s of work twice with nowhere to put the
      result; with the cache it degenerates into warming it at the right moment,
      which is a small feature rather than a system. Two triggers earn their
      keep, and only two: (a) opening a feature editor is a genuine declaration
      that the prefix below it is stable for as long as the dialog is open, so
      warm 1..N-1 and let the commit cost one feature's work; (b) dragging the
      timeline rollback marker is a walk through prefixes that are already cache
      keys, so warm the neighbours of the current stop. Register/document hover
      prefetch is standard TanStack Query and worth nothing against these
      numbers — do not bother.
      TWO CONSTRAINTS, both non-negotiable. **A speculative body must never be
      publishable**: if a warm result is ever served for a tree it does not
      exactly correspond to, that is the silent-wrong-geometry class this repo
      has closed four times, so warming must be a distinct entry point from
      evaluate. And **prefetch hides latency without reducing work** — it cannot
      bend the N^1.85 curve, and on 4 cores with several users uncancellable
      speculation is a self-inflicted DoS, so it needs a budget and real
      cancellation.
      Acceptance: a measured drop in perceived edit-commit latency at N=100 and
      N=200 with the CPU budget stated, plus a test that a warmed prefix cannot
      be returned as an answer. [src: founder question 2026-07-31 · docs/PERF.md]
- [x] (P2, S) **"Fit model" frames the CANVAS, not the VISIBLE viewport — a
      big part is clipped by its own panels. FIXED 2026-07-31** (frontend-builder).
      `viewport/fitFraming.ts` measures the live DOM (every docked element carries
      `data-viewport-chrome`, plus the in-canvas reference cube, which has no rect
      of its own), charges each obstruction to the ONE edge that leaves the largest
      free AREA, and the rig frames into that rect and slides the orbit target so
      the part sits in its middle. A panel that collapses announces itself and the
      fit re-runs — but only while the modeler has not taken the camera by hand
      since, because yanking someone off a detail they zoomed into would be a worse
      defect than the one being fixed. The fit DISTANCE is now solved from the
      subject's projected corners under the real perspective (depth included: the
      near end of a long part projects wider — an orthographic first cut measured
      51px of overhang on a 260mm rail), replacing the fixed 1.75x-diagonal rule
      that was blind to both the frame and the aspect ratio. `view-fit.spec.ts`
      fits three aspect ratios and asserts the body's projected bbox — read from
      canvas PIXELS, not from the same arithmetic — lies inside the rect on all
      four sides; mutation-verified (framing the canvas instead fails 4 of 5).
      Shots `viewfit-{before,after}-{1440,1366}.png`.
      [src: founder capture 2026-07-31]
- [x] (P3, XS) **The ViewCube is clipped by the window edge and the timeline
      strip. FIXED 2026-07-31** (frontend-builder). The inset was 64px against a
      cube whose ISOMETRIC silhouette is ~√3 wider than its face, so its lower
      corner and the FRONT/RIGHT labels sat hard on the frame edge; it is now 96px,
      which also puts it on the same 12px gutter the ViewBar and the panels use.
      Its footprint is registered as a fit obstruction in the same pass, so a part
      can no longer be framed underneath it either.
      [src: founder capture 2026-07-31]
- [ ] (P2, S) **Promote the durable EDGE tier into `geometry.kernel.edges`** (kernel
      territory). N1's two-tier resolver ships in `geometry.drawings.anchor` because
      the kernel module was held by another agent that batch; the predicate,
      tolerances and error taxonomy are already the kernel's, so `resolve_edge`
      should carry the tier and the drawings wrapper should shrink to
      "resolve + report the tier". Then a picked-edge FILLET/CHAMFER survives the
      same everyday edits a dimension now does (today they still hard-fail on a
      resized/moved edge). Acceptance: one resolver, one set of tests, a
      fillet-on-a-widened-plate regression. [src: topological-naming §11]
- [x] (P2, S) **Frontend half of N1/N2 — say it on screen, not only on the print**
      (frontend). DONE 2026-08-01: the sheet already stamped the composer's words
      beside a broken marker (`6cc89b1`); this adds the two surfaces that were
      still missing and the panel tier that dropped both. `ComposedSheet.layout_issues`
      now raises a **sheet check strip** above the paper (composer's own sentences,
      per-row Auto-place that resets exactly the hand-placed views of the pair, an
      advice line where no reset would help) AND stamps the same
      `drawing-layout-issue` banner on the DOM sheet the three serializers use, so
      the client SVG export carries it too. `anchor.tier == "durable"` stamps a
      dashed RE-ANCHORED badge with one-click **Confirm** (append-then-delete;
      `drawing/anchorHeal.ts`), and an unresolved dimension's typed reason reads in
      the panel. Gate: `e2e/drawing-reanchor.spec.ts` resizes a dimensioned part
      100 -> 120 and reads `120.000` in-app, then confirms the reference.
      [src: AUDIT-PRODUCT 2026-07-30 N1/N2]
- [ ] (P3, S) **A sheet too small for its part is still silent.** The N2 collision
      check measures view-vs-view, not view-vs-BORDER, so a part that outgrows its
      sheet hangs over the frame with no diagnostic. Wants the honest pair: a
      `views_off_sheet` issue AND an auto-fit scale suggestion (the sheet already
      has a fit-scale control), not just a warning. [src: AUDIT-PRODUCT 2026-07-30]
- [ ] (P3, S) **A dimension on a corner ROUND's arc cannot re-anchor.** Changing R4
      -> R6 moves the arc's centre, so the circular invariant (centre + angular
      station) does not hold and the dimension fails honestly rather than
      re-measuring a differently-placed arc — the documented limit of stage-1
      naming. The fix is adjacency ("the arc tangent to these two faces") = stage-2
      provenance (topological-naming §2d), not a looser epsilon.
      [src: topological-naming §11]
- [ ] (P2, M, recurring) Model-a-REAL-part dogfooding gate — once per phase
      (or ~quarterly), an agent models a complete real product end-to-end
      through the actual app + APIs, verifies against closed-form analytics,
      ships the full package, files every friction point. WB-64 (pass #1,
      2026-07-20) and TB-1 (site toolbox, pass #2, 2026-07-20) both ran; the
      2026-07-23 product-audit pass doubles as a bolted-assembly check (found
      the STEP-export/interference/import gaps now leading Ready). **Pass #3 ran
      2026-08-01 — imported-STEP remix (NEMA 17 vendor plate), docs/QA-REVIEW.md:
      seven closed-form comparisons all exact (vendor rev-B/rev-C re-anchoring to
      12 s.f.), six defects filed QA3-1..6, two of them P1 ergonomics that make
      the scenario uncompletable in the UI.** Next scenario due: spline/loft
      ergonomic handle (surfacing). [src: WB-64 retro]
- [ ] (P2, S) SM-fmt-1 — bend-table ONE format, ONE layout pass (frontend +
      geometry). Pre-format display-ready cell strings into `ComposedBendTable`
      server-side (`cells: list[list[str]]` alongside numeric `rows`) so
      `DrawingSheet.tsx` and all three serializers become a pure layout pass over
      shared strings, closing the Python↔TS drift risk the current
      comment-anchored spec only mitigates. Acceptance: DOM `BendTable` and
      SVG/PDF/DXF render identical cell text from the same server strings; byte
      goldens updated + the cross-serializer consistency test still passes.
      [src: docs/UI-REVIEW.md 2026-07-19 P2]
- [ ] (P2, L — spike first, S) Kernel: helical sweep → threads. Any screw closure
      is unbuildable today; OCCT helix wire spike, then size the feature slice
      (pitch, turns, profile, handedness, taper). Sequence after the sheet-metal
      + assembly-interop commitments ahead of it. [src: WB-64 retro; competitive]
- [ ] (P2, M) Assemblies — RECURSIVE / indented BOM (documents) — the
      follow-up to the flat v1 BOM read-model. Expand rigid sub-assembly
      instances into their own lines, rolling quantities through the nesting
      (a part appearing N× in a sub-assembly instanced M× rolls up to N·M),
      with an indent/level or parent-ref shape so the client can render an
      indented tree. The flat aggregation + `BomLine` DTO + acyclicity
      guarantee already exist; this walks the (acyclic) sub-assembly graph
      and merges lines. [src: design/assemblies.md; ROADMAP Assemblies
      residual]
- [ ] (P2, M) Units — sketch-dimension + roll-up unit display (follow-up to
      U2). Sketch driving/driven dimensions (`ConstraintGlyphs`/
      `DimensionForm`) still enter/read canonical mm because their values are
      stored EXPRESSIONS solved server-side (`width/2`, named dims) — unit-
      aware parametric expressions are a distinct design problem. Mass/
      volume/area/extents roll-ups + the box-demo form also stay mm (design
      §"out of v1"). Wire both once the expression-unit model is designed.
      [src: docs/design/units.md §"out of v1"]
- [ ] (P2, M) Viewport makeover Batch 3 remainder / deferred slices —
      per-face pick highlight + tree↔FACE linking (blocked: `OverlayResult`
      has no face→feature attribution — needs a geometry-service slice
      attributing B-rep faces/edges to their source feature; frontend wires
      once it exists); live ghost previews (datum plane cheapest, then
      extrude/pattern; deferred whole to avoid a half-built preview);
      empty-viewport origin triad + resting datum sheets, and parts-home
      thumbnails (needs a last-evaluated-mesh snapshot pipeline). Three
      independent slices bundled here pending split when picked up. [src:
      UI-REVIEW 2026-07-16 remediation items 10–13]
- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4**, remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism
      gate as existing goldens. [src: engineering-auditor F4, geometry-qa]
- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]
- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]
- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2**, now also `/overlay` — 3
      non-fetching callers) — thread a bool through `evaluate_tree` so
      `export_tree`/measure/overlay (which never fetch the GLB) don't churn
      the 64-slot mesh LRU with never-fetched entries, evicting live
      interactive-session meshes. Acceptance: export/measure/overlay
      requests no longer call `store_mesh_glb` (test asserts cache occupancy
      unchanged after N calls); evaluate-for-viewport path unaffected. [src:
      engineering-auditor F2]

## Later (P3)

- [ ] (P3, XS) **QA3-4 — the PUBLISHED overlay contract still promises the
      pre-PERF-4b glTF layout.** `OverlayFace.feature_id`'s description (py-kit →
      `packages/contracts/gateway.openapi.json`) tells clients "each face's `index`
      is its `body.faces()` ordinal (== the GLB primitive ordinal, one glTF
      primitive per B-rep face)". Since `d8a4126` that holds only on the UNFUSED
      encoding; below 12 triangles/face the ordinal must be recovered from
      `extras.LOFT_face_triangles`. Measured: 11 B-rep faces arriving in 6
      primitives. `apps/web` does it right — the CONTRACT is what is wrong, and a
      third-party client written to it mis-highlights every sparse part. Fix the
      description + regenerate. [docs/QA-REVIEW.md 2026-08-01 QA3-4]
- [ ] (P3, M) **QA3-5 — small features are tessellated ~200x finer than the
      requested deflection, because the angular criterion is radius-independent**
      (geometry). Every cylindrical face gets 126 circumferential segments
      whatever its radius. Measured max chord error against the 0.1 mm
      `DEFAULT_LINEAR_DEFLECTION`: Ø3 hole 0.000467 mm (214x finer), Ø5.2 bore
      0.000808 (124x), Ø10 bore 0.001554 (64x), Ø22 boss 0.003419 (29x). A 24-face
      plate meshes to 4 846 triangles, ~1 500 of them in six cylinders under 6 cm²
      total, and the density pushes such parts to 202 tris/face — well past
      PERF-4b's threshold of 12, so they decline the fusion that would have removed
      their per-face JSON. A vendor STEP with a hundred tapped holes pays it on
      every hole. Acceptance: honour the linear deflection as the binding criterion
      on small radii (or scale the angular one by radius); goldens re-baselined in
      the same commit since `mesh_glb_id` is a content hash. [docs/QA-REVIEW.md
      2026-08-01 QA3-5]
- [ ] (P3, XS) **QA3-6 — `data-camera-pos` reads like a live camera hook and is
      not.** It is stamped only on a programmatic view SETTLE (fit / view command),
      never on a user orbit or pan, so a touch-orbit probe that WORKS looks broken
      — it produced a false positive during dogfooding pass #3 before being
      root-caused. Either stamp it on control change or rename it to say what it
      means. (`import-remix.spec.ts` asserts on a canvas raster fingerprint
      instead.) [docs/QA-REVIEW.md 2026-08-01 QA3-6]

- [x] (P3, XS) **`MAX_PROVENANCE_FACES`' docstring still files a fix that shipped.**
      DONE 2026-08-01 (orchestrator, same day it was filed): the four lines now
      describe the shipped design — attribution is O(final faces) since PERF-5b —
      and say what is still TRUE of the arithmetic, namely that the budget counts
      summed snapshot faces because that bounds the work of PRODUCING the
      fingerprints. So 30 000 is headroom against the recording pass, not against a
      quadratic attribution pass. Filed by kernel-architect, which correctly
      declined to reach into `packages/**` outside its territory.

- [ ] (P3, S) **A lost dimension's caption can overrun into a neighbouring view
      — and it does so identically on the exported sheet** (kernel/drawings).
      `DimensionGlyph` now stamps the server's `ComposedDimensionError.message` at
      `dim.text`, which is right; the placement is not. `compose.py`'s
      `_DIM_ERROR_TEXT_DX` offsets the caption by a fixed amount with no width
      measurement and no collision check against the neighbouring view's extents,
      so a long message crosses the gutter. Visible in
      `docs/screenshots/drawing-dim-lost-after-1440.png`. The fix belongs in the
      COMPOSER, not the client: the SVG export has byte-identical placement, so a
      client-side nudge would make screen and print disagree — which is the defect
      class this repo keeps closing. Acceptance: the caption is placed against the
      view's measured extents (the N2 collision machinery already exists), with a
      compose golden that has a caption long enough to have overrun.
      [src: handback from the #58 settings slice, 2026-07-31]
- [ ] (P3, M) Settings rows that need a PROPERTY before they can be rendered
      (frontend-builder, 2026-07-31 — deliberately omitted from the shipped
      `/settings` sheet rather than faked). Each needs its backing first:
      **angular unit** (`packages/design/src/units.ts` is length-only — no angular
      vocabulary, and angles are authored in degrees everywhere), **display
      precision** (`formatLength` takes `maxFractionDigits` but nothing carries a
      user value down to the readouts), **grid/snap step** (a sketch-store constant
      being made configurable in a concurrent slice — read THAT value, never define
      a second one), and **document-scope settings generally**: the sheet is
      application-scope only because a document setting needs an open document, so
      the unit/material controls stay in the workspace until there is a
      document-settings surface there. [src: founder #58, scoped]

- [ ] (P3, S) Drawings compose: the failed-view dashed box overlaps its error
      text with the view caption (e.g. "FLAT PATTERN") — small `_emit_view`
      polish; changes byte-pinned compose goldens, so it rides its own slice.
      Split from the shipped hem-on-flange flat-pattern fix (2026-07-22).
      [src: founder dogfooding — TB-1]
- [ ] (P3, S) STEP import parse-worker — cap parse WORKING-SET memory + config
      hardening (code-review 🟢 on `f5a9038`): the STEP subprocess now bounds CPU
      time (`RLIMIT_CPU`) but NOT resident memory — only the 16 MiB _input_ is
      capped, so an adversarial <16 MiB file can still balloon OCCT's in-memory
      model. Add `RLIMIT_AS`/`RLIMIT_DATA` alongside the CPU limit in
      `_step_parse_worker._apply_cpu_limit` (sized not to reject a legit large
      part), and (a) map an OOM-`SIGKILL` to a memory/parse-failure code rather
      than `import_parse_timeout`, (b) clamp/validate a non-finite
      `STEP_IMPORT_TIMEOUT_SECONDS` in `GeometrySettings` (an inf/nan budget
      currently degrades every import to `parse_failed` via an uncaught
      `math.ceil`). Pre-existing, non-attacker-reachable footguns + a real
      memory-DoS gap. [src: code-reviewer]
- [ ] (P3, S) Drawings D5/D6 — portrait orientation (consumer exists, no
      authoring — add to the sheet-size UI) + multi-sheet (only `sheets[0]`
      composed/exported; note the v1 limit in the export route docstring or
      gate extra sheets). [src: AUDIT-ENGINEERING.md D5/D6]
- [ ] (P3, S) Drawings: flat-pattern auto-fit to the sheet — needs the
      UNFOLDED blank extents (not the 3D bbox `fitScale` reads off the part
      evaluate), a distinct data source from the shipped standard-view fit.
      [src: founder dogfooding — WB-64]
- [ ] (P3, S) Drawings: projected-coincident circle edges create ambiguous
      pick targets + duplicate dims (founder dogfooding 2026-07-20). Dedupe
      projection-coincident pick targets (prefer the visible edge) and warn on
      an exact-duplicate dimension. [src: founder dogfooding — WB-64]
- [ ] (P3, M) Exploded views + assembly drawings — the presentation half of
      the assembly; sequence after the assembly-STEP/interference/import P0/P1
      trio and Drawings' own assembly-view work (Ready). [src: AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, S) Part-version pinning for assemblies — instances track a part's
      live tip today; immutable part versions give deterministic, frozen
      assemblies. [src: AUDIT-PRODUCT.md 2026-07-23]
- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5**) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs. [src: engineering-auditor F5]
- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. [src: competitive]
- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim
      collision (showcase F3) — backend behavior is correct (OCCT refuses
      the collision), this is discoverability only. [src: product-auditor
      showcase-QA F3]
>>> ATTRIBUTION NOTE (orchestrator, 2026-07-30): the three P3 items below were
>>> filed by kernel-architect as SH-1 follow-ups, but landed in commit `33b1b5a`
>>> — an orchestrator commit about an unrelated gate — because I ran
>>> `git add docs/BACKLOG.md` while their uncommitted hunks were in the file.
>>> The protocol is stage YOUR hunks, never a shared doc wholesale. No work was
>>> lost; the authorship in git history is simply wrong, and `33b1b5a`'s message
>>> does not mention these items.

- [ ] (P3, S) A typed `warnings` channel on `FeatureResult` + a distinct
      `shell_pinched_wall` code — the honest follow-up to SH-1 (GEOMETRY-QA
      2026-07-30). A thickness of exactly half an internal wall is refused today
      under `shell_thickness_too_large` because the wire has no way to say
      "built, but read this"; the kernel already computes the slit's area and
      position, so the only missing piece is the schema. py-kit + generated
      clients + tree-panel copy — NOT a kernel change. [src: kernel-architect,
      SH-1]
- [ ] (P3, S) Kernel: bucket `find_zero_width_slits` by support plane if a shell
      of a many-FACE body ever becomes a real workflow. The pair test is O(N^2)
      float arithmetic — measured ~1.2 us/pair (0.56 ms on the 11-face golden
      tray, 6.3 ms on a 102-face comb), so a few hundred faces is still cheap
      next to `MakeThickSolid`, but an imported STEP part with thousands would
      not be. Bucketing must not quantise the comparison bounds (a missed
      bucket = a missed slit). [src: kernel-architect, SH-1]
- [ ] (P3, S) Sheet metal: floor `SheetMetalHemParamsV1.bend_radius_mm` at the
      kernel linear tolerance (1e-4 mm). A closed hem's air gap is `2 x radius`
      and the schema only requires `> 0`, so radius 1e-6 ships a body whose two
      layers are 2e-6 mm apart — a zero-width slit by the kernel's own tolerance
      (300 mm² measured), reported `ok`. Pinned live by
      `test_observed_limit_a_sub_tolerance_closed_hem_ships_a_slit`; not
      reachable by a sane author in mm units, and the fix belongs in the py-kit
      schema (a validation 422), not a per-verb kernel probe. [src:
      kernel-architect, SH-1 sibling audit]
- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow —
      needs a design note first (what "a selected region" means for
      `MakeThickSolid`). Not urgent: showcase routed around it. [src:
      qa-tester showcase-QA]
- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded; a real
      engineering/scaling concern once imported-part assemblies bloat the tree
      (re-confirmed 2026-07-23). [src: roadmap, step-import.md; AUDIT-PRODUCT.md
      2026-07-23]
- [ ] (P3, L) STEP import v2: IGES, assembly product-structure, sew/repair
      healing — (1) IGES as a second import format; (2) named ASSEMBLY
      product-structure (STEP AP242 hierarchy → an assembly of instances,
      distinct from MB-4b's flatten-to-lumps); (3) a real sew/repair healing
      report. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]
- [ ] (P3, S) Sheet-metal bend-tree unfold — optional hardening (code-review
      🟢 on `66aee0a`): (a) add a RUNTIME invariant inside `_unfold_bend_tree`
      asserting the assembled union-loop shoelace area ≈ summed `flat_area_mm2`
      (raise `UnfoldOverlapError` otherwise) so "the outline tiles the blank" is
      load-bearing at runtime, not only in the golden tests — closes the one
      theoretical path (flange vs non-adjacent BA-strip overlap merging into a
      clean loop) the flange-rect-only overlap gate doesn't cover; (b) note the
      `_face_key` normal-6dp/centroid-4dp tree-node rounding (fine for mm-scale
      parts, in-run-only key). Neither demonstrated on a real body. [src:
      code-reviewer]
- [ ] (P3, S) Sheet-metal corner relief — optional hardening (code-review 🟡/🟢
      on `d1aaadd`): (a) an oversized relief (`size_mm`/`relief_ratio` developing a
      notch deeper than ~half the shared flange width) produces a VALID body but
      fails only at draw time on the relieved flat-pattern unfold — move the check
      EARLIER, into the corner-relief evaluator, so it degrades to a typed
      `corner_relief_failed` at feature-eval time (matching the honest-degradation
      contract) instead of surfacing downstream in the flat-pattern view; (b) 🟢
      `cut_relief_tools`'s `(body, tools)` split is currently exercised only through
      `apply_corner_relief`'s single-relief path — YAGNI signature, fold back inline
      if no second caller materializes; (c) 🟢 note the relief-notch `content_hash`
      is order-sensitive on the tool subtraction sequence (deterministic today via
      the feature-tree order, but not intrinsically order-free). None blocks a real
      user model; all are out-of-scope-input / internal-shape notes. [src:
      code-reviewer, corner-relief multi-corner review]
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents `HTTPValidationError`) [src:
      kernel-architect]
- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening. [src: code-reviewer]
- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic. [src: code-reviewer]
- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's
      core wedge, not urgent: doesn't flip a current ❌ row since Loft's
      parametric core isn't finished yet. [src: competitive]
- [ ] (P3, L) MB-4 tail (deferred) — per-lump pick/highlight, explicit
      per-feature target-body ref, a "split bodies" feature. The stage-2
      provenance naming that makes boolean-edge refs structurally
      non-retargeting (topological-naming.md §10) is the standing unblock.
      [src: docs/design/multi-body.md]
- [ ] (P3, M) Datum planes — angled (about an edge/sketch line), three-point,
      tangent-to-cylinder, normal-to-curve kinds. Each a future additive
      `DatumParams` kind, same funnel as `midplane`/`offset_from`. [src:
      founder, docs/design/datum-planes.md]
- [ ] (P3, S) Drawings — manual drag-to-place of the dimension line (v1
      auto-places at a fixed offset). [src: design/drawings.md §3.1]
- [ ] (P3, S) Drawings — pickable-edge discoverability at rest. Dimensionable
      edges only reveal their pickability on hover/focus; add a quiet
      resting cue for a first-run user. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — Dimensions-panel row ↔ view/sheet association. Add a
      view tag + hover→geometry-highlight (the sketcher/measure precedent).
      [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, M) Drawings — pickable edges as individual tab stops don't scale.
      Move to a roving-tabindex / "enter the sheet then arrow between edges"
      pattern. [src: docs/UI-REVIEW.md 2026-07-17]
- [ ] (P3, S) Drawings — hidden-edge provenance can tag the FAR coincident
      edge on a genuine hidden coincidence (no visible edge there). The
      visible path already refuses such guesses; the hidden path should too.
      Not reachable from any shipping part. [src: geometry-QA of `5e16f9d`]
- [ ] (P3, S) Drawings — body-only eval path (drawing-eval wastes
      tessellation). `evaluate_drawing_views` reuses `evaluate_tree`, which
      unconditionally tessellates + stores a GLB the projection-only path
      never fetches. DRY-sanctioned for now; add a body-only eval entry
      point when drawing-eval volume makes it matter. [src: code-review of
      `d65caff`]
- [ ] (P3, S) History-tree drag-reorder — distinct from the rollback bar
      (which moves the build point, not an action stack) and from Feature
      suppress (promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src:
      product-auditor Pass 2]
- [ ] (P3, M) 2-direction linear pattern — pattern breadth gap (mirror-feature
      promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src: product-auditor
      Pass 2]
- [ ] (P3, S) A friendlier `boolean_failed` error message (today's is the
      generic OCCT-raise catch-all). [src: product-auditor Pass 2]
- [ ] **SPECULATIVE — not sized, not sequenced, candidate future vertical
      only.** AEC/BIM domain layer (Revit-class: walls-that-host-openings,
      levels/grids as spine, IFC interop, schedules) — see
      `docs/design/aec-bim.md` for the full pre-greenlight scoping. Honest
      verdict there: a legitimate 2027+ platform bet comparable in size to
      everything Loft has shipped through Phase 4, gated on a domain
      correctness bar (code/egress/energy) the team doesn't have — NOT a
      near-term pillar, does not compete with Phase 4b/5 for attention.
      [src: founder]

## Blocked (environment/timing — not build-blocked)

- [x] (P2, S) Verify full `docker compose up` runtime — **DONE 2026-07-25**
      (platform-builder): unblocked by running it where Docker works, CI —
      `deploy-path` run `30142627371`, `success`, 86s, 9 checks passed.
      `scripts/compose-smoke.sh` (workflow `deploy-path`, `just
      compose-smoke`) builds + boots the base stack, migrates both schemas
      from the images, drives register → sketch → extrude → evaluate → mesh
      fetch → STEP export over the gateway port only, and asserts the internal
      ports are closed. Found + fixed: gateway/documents shared one database
      although both alembic trees start at revision `0001` (second migration
      silently no-ops), and no host-toolchain-free way to create the schema.
      [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended.
      [src: retro]

## Done — archive

Full narrative evidence lives in `docs/ROADMAP.md` (Phase 4/4b sections) and
`CHANGELOG.md`; one line per item below per token economy.

### Recently shipped (2026-08-08)

- **SEL-6b — a hidden body stops OFFERING picks, not only eating them.** The
  mirror half, raised by review: `/overlay` has no notion of visibility, so a
  switched-off body's edges stayed hoverable along the whole 24 px band corridor
  and its faces selectable via their centroid marks. New pure
  `apps/web/src/viewport/hiddenPicks.ts` decides the offer once for every overlay
  — faces from `pickHiddenFaces`, edges/points by weld bucket (shared `weldKey`
  with `bodyPartition.ts`), ambiguity always resolving to OFFER. Wall hidden on
  `seedOccludedEdgePlate`: **24 edge marks -> 12, 12 face marks -> 6**, drawn
  body unmoved, and none of the wall's edges answer over the space it vacated
  (13 did). Mutation-verified three ways, including marks-filtered-but-band-not.
- **SEL-6 — a hidden body in front no longer eats the pick for the body behind
  it.** The SEL-4 guard could only REFUSE the hidden triangle, never see past it:
  three never reads `material.visible` (only `material.side`), and r3f keeps one
  hit per object, so the drawn face behind was never offered. New pure
  `apps/web/src/viewport/pickRaycast.ts` drops hidden triangles inside `raycast`,
  before r3f dedupes — one change for every overlay plus `ModelMesh`'s own face
  hover, and `PickTriangle`'s `hidden` kind and `edgeBand`'s `surfaceOccludes`
  both go away. Shell reachability with the wall hidden: **7.4 % -> 96.3 %**,
  controls unmoved; the occlusion test starts applying again behind a hidden
  body (a buried edge answered before the fix, not after). Three e2e legs plus
  the node-side two-quad raycast case, all mutation-verified.

### Recently shipped (2026-08-01)

- **QA3-1 — you can drill where you want now.** Placement was two points, the
  face's area CENTROID and its corners, so on the dogfooding plate (whose centre
  IS the Ø5.2 shaft bore) a 5th mounting hole was impossible through the UI. The
  point is now dialled in: X/Y cells in the face's frame re-checked on every
  keystroke, a live material verdict that NAMES the opening a bad point fell
  into, and a snap to every circular edge in the face's plane (concentric /
  bolt-circle). The frame is STATED rather than implied — its zero is the part
  origin projected onto the face, never the area centroid, because the centroid
  moves and that is QA3-2's mechanism; the card says it and the viewport draws
  it on the model. The typed `hole_off_body` is untouched and still reachable:
  the client check WARNS, it never blocks the write. e2e drills the 5th hole at
  (15.5, 0) and reads 14 179.47 mm³, closed-form exact.

- **GATE-2 — the `.dockerignore` allow-list lost an entry and only `deploy-path`
  noticed.** LIC-2 added `scripts/corresponding_source.py` to the runtime `COPY`
  (the licence gate imports it) with no matching `!` negation, so the daemon
  resolved that source to nothing and all three image builds failed on `42c4a0c`
  and `4c2fdbe`. Unreachable locally by construction — the registry is blocked,
  so the only signal was the slowest workflow we have. Negation added, and the
  class closed: `scripts/check-build-context.py` re-implements moby's
  `MatchesOrParentMatches` and asserts every Dockerfile COPY source survives
  `.dockerignore` (stdlib, no daemon, ~10 ms) in `just lint` + CI's `compose`
  job. Verified as a gate, not asserted: it reproduces the real failure by name
  before the fix, and its matcher agrees with the docker SDK's context walk on
  all 445 included entries. `--self-test` proves it can fail.

### Recently shipped (2026-07-31)

- **OBS-1 — there was no observability at all; now there is `/metrics`.** The
  release-target gap of the same shape as OPS-1: `/healthz` + `/readyz` + logs
  cannot distinguish a 26 s legitimate rebuild from an incident. Prometheus
  exposition wired ONCE in `py_kit.metrics` (Apache-2.0 client), so all three
  services inherit it: rebuild time as a histogram by `cache` × `tree_size` (2 s
  = a bucket boundary), rebuild-cache hits/misses/evictions (the per-process LRU
  is divided by worker count, not multiplied), feature failures by error code,
  STEP import duration + refusals by reason (20 s = a boundary), HTTP by route
  TEMPLATE, process/GC. Seams that cannot be bypassed; every test asserts a
  DELTA. **+30 µs/request measured** (A/B vs `METRICS_ENABLED=false`).
  `/metrics` is fail-closed outside `LOFT_ENV=dev` (bearer `METRICS_TOKEN`, 404
  without it). Guide: `docs/OBSERVABILITY.md`.

### Recently shipped (2026-07-30)

> ATTRIBUTION NOTE (orchestrator): the `#57` materials entry below was filed by
> kernel-architect but landed in commit `3248ad8` — an orchestrator commit about
> the drawings projection guard — because I ran `git add docs/BACKLOG.md` while
> its hunks were in the file. Second occurrence in one day of the same mistake,
> after I had written the recipe against it. Annotated rather than rewritten:
> agents have already rebased onto that commit. `scripts/stage-doc-hunks.py`
> now exists so the correct path is the easy one.


- **#31 — compose's projection-keyed anchors now REFUSE a repeated projection**
  instead of silently dropping a view from the print. The invariant that made it
  unreachable lives in another service's DB constraint; geometry now states and
  checks its own dependency. Mutation-verified.

- **N1 (P0) — revising a part destroyed the dimension that measured it.** Widening
  100 -> 120 made the overall-length dim `subshape_unresolved` (a 2.6 mm `!`); edges
  now get the two-tier resolver faces got in FINDINGS #3 (`drawings/anchor.py`,
  topological-naming §11) — strict, then the curve-kind invariant (line: supporting
  line + span overlap; circle: centre + angular station). Re-measures **120.000**,
  reports `anchor.tier: durable`, placement uses the re-anchored name, and an
  un-re-anchorable ref prints WORDS beside the view in SVG/PDF/DXF. A MOVED hole
  stays an honest error. Gates: `test_drawings_resize.py` + `test_drawings_anchor.py`.

- **N2 (P0) — auto-layout overlapped four views after a resize and exported it.**
  6.33 x 60.00 mm iso-over-top with 82.8 mm of sheet empty; the 0.70 mm pre-edit
  clearance WAS the diagnosis. Iso anchors are now derived from the extents they must
  clear (**every pair clears the full 24 mm gutter at 100 and 120 mm**), hand-placed
  views stay honored as intent, and `measure_layout_issues` reports
  `views_overlap`/`views_crowded` on `ComposedSheet.layout_issues` + a
  release-blocking banner in all three formats. Five compose byte-goldens
  regenerated for the clear layout; a clean sheet carries no banner ink.

- **J5 — the "backend drift guard" in `face.test.ts` could not fail for backend
  drift.** It compared a hand-copy in the test to a hand-copy in `face.ts`, BOTH
  inside `apps/web`, under a comment promising "a member added on ONE side fails
  here". It now PARSES `py_kit.schemas.features.BODY_AFFECTING_FEATURE_TYPES`
  (the `thread.test.ts` pattern: comments stripped first, since that frozenset's
  comments quote prose) with a non-vacuity guard, and the comment says what the
  gate actually does. Mutation-verified BOTH ways: a member added on the py-kit
  side fails it; a regex that matches nothing trips the non-vacuity assert.

- **J6 — the body-affecting feature-type set was declared twice, unguarded.**
  Gated rather than merged (the two constants answer different questions and
  coincide non-tautologically); the gate also asserts every member is a
  REGISTERED verb, which is what catches a rename. Mutation-verified.

- **#42 — shelling a rib at EXACTLY 2x the wall left a zero-width slit and
  reported `ok`** (SH-1). Now a typed `shell_thickness_too_large` naming both
  fixes, via ONE shared `kernel/degenerate.find_zero_width_slits` predicate;
  no heal removes a slit (ShapeFix / UnifySameDomain / self-fuse all measured).
  Knife edge proved: 1.999 ok / **2.000 refused** / 2.001 ok; new hand-derived
  golden `shell-pinch-boundary-...-t1.9`; all 60 tree goldens slit-free (new
  cross-verb gate). Evidence: GEOMETRY-QA 2026-07-30.

- **J8 — the DoD's "geometry gates" ran 11% of the geometry suite.**
  `scripts/e2e.sh` leg 1 was a hand-listed two-file allowlist that excluded the
  309-test composition matrix; now the whole directory. Measured 233 -> 2200
  tests selected. CI's repo-wide pytest was never blind — the LOCAL pre-commit
  gate was.

- **F1 — the sketch Exit destroyed unsaved work while the caption blamed Esc**
  (which actually SAVES). Esc chip moved to Save; Exit states the count it would
  discard and asks first; prompt is derived so it cannot outlive the work.
  9 component tests, mutation-verified (old code fails 5).

- **F2 wire half — the body's provenance is on the wire.** `PartResponse.
  tree_version` (current) + `EvaluateTreeResult.tree_version` (built-from) folded
  by one shared `is_stale_for_tree`; frontend readout filed as the follow-up.

- **CM-5 — `body`-scope mirror after a revolve/sweep/loft CUT filled the void**
  (FINDINGS #2 class, silent wrong geometry). One line in the shared `_cut_active`
  funnel; matrix predecessor axis now derived from `FeatureTypeRegistry.models()`
  so a new cut verb cannot ship matrix-blind. 3 goldens, 774 kernel tests green.

### Recently shipped (2026-07-25 batch — engineering audit H findings)

- [x] (P0, S) **Regression A — the resilient face re-match silently MOVED the
      resolved plane origin.** Tier 2 (`coplanar_signatures_match`) matches on the
      supporting plane alone, but `resolve_face_plane` returned the matched
      record's plane — origin = the CURRENT area centroid. Measured on the fixture
      (40×40×10 plate, hole at (8,8) Ø6→Ø8): the shared top face's centroid moves
      (-0.1439,-0.1439) → (-0.2595,-0.2595), so every sketch/datum/assembly mate on
      that face translated 0.1156 mm in x and y with no error (pre-`2b6b72e` it was
      an honest `subshape_unresolved`). Tier 2 now re-anchors at the STORED centroid
      projected onto the matched face; tier 1 unchanged. 2 regressions.
      [src: code-review 2026-07-25 regression A]
- [x] (P1, M) **H4 — per-face provenance taxed every compute path and scanned
      quadratically.** (a) `evaluate_tree(..., record_history=False)` by default,
      so only `/overlay` funds the snapshots — the other 8 call sites retain 0
      intermediate B-reps (goldens measured 4/3/2 → 0) with byte-identical GLB.
      (b) The matcher is one spatial hash over all snapshots keyed
      `(surface, quantised centroid)`: 600-face body 180300 → 600 comparisons;
      8.83 s → 1.82 s at 4800 faces, now linear and snapshot-count independent.
      (c) `MAX_PROVENANCE_FACES = 8000` (py-kit, G2 idiom, contract-visible)
      DEGRADES to null attribution past the bound rather than 422-ing the whole
      picking overlay. 5 new geometry tests + an `overlay` benchmark group.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H4]
- [x] (P0, S) **Regression B — the cut-aware mirror silently NO-OPPED the two
      canonical mirror workflows.** `_prev_cut_tools` fires on ANY preceding
      extrude-cut/Hole and `_evaluate_mirror` then took `mirror_cut`
      unconditionally; `mirror_cut` never verified a removal happened, so a
      reflected tool landing outside the body cut nothing and the untouched body
      came back `ok`. Measured: a 40×40×20 block + 10×20×10 pocket mirrored about
      its own +X face (x=40) stayed 30000 mm³ at x∈[0,40]; now 60000 mm³ over
      x∈[0,80] with a pocket in each half. Fix: a reflected removal that cannot
      reach the body (topological common, no epsilon) falls back to
      `mirror_union`, whose reflection already carries the body's own cuts —
      deliberately NOT union-then-recut, which would weld shut any EARLIER cut.
      New golden `mirror-cut-clearing-plane-block-40x40x20` + 3 regressions.
      [src: code-review 2026-07-25 regression B]

- [x] (P1, S) **H2 — a sheet silently mixed source documents and scales.**
      `ComposeDrawingRequest` carries ONE source + ONE scale, so a sheet whose
      views named different parts/scales exported EVERY view from `views[0]`'s
      part at `views[0]`'s scale (reachable via the gateway API / Phase-5 agent
      surface). Enforced instead of guessed (design decision (a), drawings.md
      §2.2): documents refuses the divergent write
      (`sheet_source_document_mismatch` / `sheet_view_scale_mismatch` 422 in
      `create_view` + the `update_view` re-scale path) and the gateway
      `_assert_single_source` re-checks the READ before any part/compose hop
      (legacy rows). 8 regressions (documents + gateway).
      [src: AUDIT-ENGINEERING.md 2026-07-25 H2]
- [x] (P2, S) **H3 — duplicate view projections collapsed at every layer; the
      drag-to-place PATCH wrote to the WRONG row.** Now `uq_views_sheet_projection`
      UNIQUE `(sheet_id, projection)` (migration `0011`: de-dupe keeping the lowest
      `order_index`, dense renumber, then the constraint) + ORM twin + typed
      `duplicate_view_projection` 422 on create/re-projection; web keys per VIEW ID
      via the new pure `drawing/views.ts::viewRowsByProjection` (first-write-wins).
      3 documents + 2 migration + 3 web regressions. Residue routed to the kernel
      agent: `compose.py::_resolve_view_anchors` still keys anchors by projection.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H3]
- [x] (P2, S) **H5 — sheets-per-drawing was the one work bound G2 missed**, and
      `_tree_response` was N+1 over it (3 queries PER SHEET, in the drawing GET and
      every delete route). `MAX_DRAWING_SHEETS = 100` + `max_length` on
      `DrawingTreeResponse.sheets` + documents `sheet_limit_exceeded` 422 twin (the
      G2 idiom); `_by_sheet` collapses the reads to ONE `sheet_id IN (...)` query
      per child table → 4 queries per tree. Contracts regenerated.
      [src: AUDIT-ENGINEERING.md 2026-07-25 H5]
- [x] (P2, S) **CR-6 — the multi-sheet export filename did not name the sheet**, so
      exporting sheets 1 and 2 of one drawing gave `plate.pdf` + `plate (1).pdf`.
      The gateway (the only hop that knows WHICH sheet composed) now sets
      `Content-Disposition` itself: `<drawing>-<sheet>.<ext>` for a multi-sheet
      drawing, unchanged `<drawing>.<ext>` for a single-sheet one. Real gateway
      regressions (the web `exportDrawing.test.ts` header was a mock).
      [src: code-review CR-6]

### Recently shipped (2026-07-24 batch)

- [x] (P1, S) FINDINGS #9 geometry enabler — per-face feature provenance
      (`services/geometry`, `packages/py-kit`). Evaluation snapshots the body after
      each ok body-affecting feature; `attribute_faces` tags each final face with
      the feature that created/last-modified it (fingerprint = surface+area+centroid,
      reusing the stage-1 face tolerances). Additive `OverlayFace.feature_id`
      (body.faces() order == GLB primitive order) lets the frontend map a feature
      id → its face set. Test `test_provenance.py`: hole wall → hole, base sides →
      extrude; goldens/STEP byte-stable. Frontend consumption stays open below.
      [src: FINDINGS.md #9]
- [x] (P2, S) FINDINGS #16 undo bypasses cross-doc protection (`services/documents`).
      Part undo/redo restored a datum a drawing section view references, silently
      breaking the view (`failed: true`). Fix: undo/redo restore now runs the SAME
      feature-level cross-doc guard as a direct delete — one shared detection
      (`parts.section_view_feature_refs`) both paths route through (DRY); direct
      delete → 409 `feature_has_dependents` (now lists the drawing, kind="drawing"),
      undo → 409 `part_restore_conflict` (mirrors the assembly restore guard).
      Regression test: section view on a datum blocks both delete and undo, datum
      survives. [src: FINDINGS.md #16]
- [x] (P0, M) FINDINGS #1–#2 cut-aware pattern + mirror (silent-wrong-geometry
      pair, `services/geometry`). Patterning a Hole duplicated the whole body
      (59497.3 vs 34492.04) and mirroring a holed plate about its midplane filled
      the hole to a solid brick (32000.0 vs 29989.38): both inferred a cut source
      but recognized only extrude-cut. Fix: `_prev_cut_tools` also returns a
      Hole's captured bore(+recess) tools (`state.last_hole_tools`, no post-cut
      face re-resolution); mirror gains `mirror_cut` (reflect+remove the cut) vs
      `mirror_union`. Two composed goldens (pattern-of-hole tol 1e-9, mirror-of-
      holed-plate tol 1e-8) assert analytic volume + exact topology, fail on the
      old behavior; `hole.py` tool builders factored (DRY). [src: FINDINGS.md #1–#2]
- [x] (P0, M) FINDINGS #3 same-face reference resilience (`services/geometry`).
      Editing Hole1 Ø6→Ø8 orphaned a same-face Hole2 (`subshape_unresolved`): the
      planar-face signature pinned area+centroid, which any in-plane edit shifts.
      Fix: two-tier match — strict signature first, then (only on zero strict
      matches) a resilient coplanar re-match on the strongest invariant alone
      (same-sense normal + coincident supporting plane `centroid·normal`), shared
      by every face resolver. Still honest: distinct coplanar faces →
      `subshape_ambiguous`, absent plane → `subshape_unresolved`. Regression: the
      edit-A-then-B-resolves scenario at the resolver AND through `/evaluate`.
      Frontend re-pick affordance keys off the unchanged typed
      `subshape_unresolved` FeatureError. [src: FINDINGS.md #3]
- [x] (P3, S) FINDINGS #23 bore negative-diameter guard (`services/geometry`).
      `bore_tool`/`bore_hole` reject a non-positive diameter with a typed
      `HoleInvalidDiameterError` (feature layer → `hole_invalid_diameter`) instead
      of a raw OCCT raise; xfail flipped to a real assertion. [src: FINDINGS.md #23]
- [x] (P1, M) FINDINGS UX P1 trio (novice flow, `apps/web`). #11 the Esc
      promise: one global window Esc handler in PartPage disarms any open
      feature editor from ANY focus (band advertised "CANCEL ESC" but cancel was
      per-editor onKeyDown — dead outside the panel); the 17 editors drop their
      Escape branch → one cancel path (DRY), pick-armed hole/datum cascade
      preserved. #12 dimension discoverability: `dimensionVerbHint` surfaces a
      quiet "[D] dimension" affordance in the sketch status bar on a single-line
      selection, reusing `applyConstraintAction`'s own acceptance so it never
      lies. #13 per-feature error copy: `friendlyFeatureError` keys
      `profile_not_closed` on feature type — an open-profile extrude reads
      extrude advice, not revolve centerline text. e2e: Esc-outside-panel
      (mirror.spec), extrude-specific copy (extrude-ui.spec), hint-on-select
      (dimension-expressions.spec) + founder shots. [src: FINDINGS.md #11–#13]
- [x] (P2, S) FINDINGS #17 units don't convert readouts (`apps/web`,
      `packages/design`). Part mass-props/bbox readouts (volume/area/centroid/
      extents/bbox) convert at the display boundary through the SAME units core
      the inputs use — new `fromMmArea`/`fromMmVolume`/`areaUnitLabel`/
      `volumeUnitLabel` in `@loft/design`; `formatVolume`/`formatArea`/unit-aware
      `formatVec3`/`formatExtents` in `apps/web`. `in` → `0.61 in³`/`5.12 in²`,
      labels follow; mm is the identity (unchanged). Unit-tested + e2e
      (document-units.spec). [src: FINDINGS.md #17]
- [x] (P2, M) FINDINGS #18 multi-sheet drawings are API-only (`apps/web`). A
      `SheetTabs` switcher (tabs + add) on the drawing page selects the active
      sheet + appends new ones via the real `createSheet` route; the active sheet
      drives the page's sheet-scoped state (setup/layout/views/dimensions/notes).
      Paper compose/export followed later (see the frontend follow-up below,
      2026-07-25) — the active sheet now composes + exports its own paper. e2e
      (drawing-sheets.spec). [src: FINDINGS.md #18]
- [x] (P3, S) FINDINGS #22 "New part" doesn't open it (`apps/web`). Creating a
      part from the register now navigates into its workspace (still filed in the
      register for next time). e2e (parts-home.spec). [src: FINDINGS.md #22]
- [x] (P2, S) FINDINGS #3-fe re-pick repair affordance (`apps/web`). A
      genuinely-unresolvable hole face shows a one-click "Re-pick face" in the
      tree error row (keys off the typed `subshape_unresolved` FeatureError); it
      opens the hole editor + re-arms its face pick so the reference re-attaches
      through the same overlay. e2e (repick-face.spec). [src: FINDINGS.md #3]
- [x] (P2, M) FINDINGS #19 viewport interaction polish (`apps/web`,
      `packages/design`). Face picks read as topology (translucent brass patch on
      the hovered/armed face plane — `viewport.facePick`); body hover is a
      perceptible quiet warm-up (`viewport.hoverSurfaceTint` + brass edges); a
      dismissible `NavCue` teaches orbit/zoom/pan above the view rail (persisted);
      the assembly scene seats each instance on its OWN contact pool (Viewport
      `groundShadow` opt-out + per-instance pools) vs one flat blob. Register
      de-templatizing deferred (brief-optional). e2e (findings-p2-shots) + founder
      shots. [src: FINDINGS.md #19 / UI-REVIEW]
- [x] (P2, S) FINDINGS #20 jargon / ergonomics (`apps/web`, `packages/design`).
      Gate copy teaches ("Draw a sketch…" not "Solve a sketch first"); Hole editor
      slides to the right edge while a pick is armed (never covers its target);
      dimension role toggle is plain ("Sets size" / "Reference" + gloss); icon-only
      undo/redo get a ≥32px comfortable target; a just-saved feature's rebuild
      error mirrors at the editor seat (`rebuild-notice`). e2e + regression green.
      [src: FINDINGS.md #20 / UX-FLOW-AUDIT]
- [x] (P2, M) Per-sheet drawing compose/export + drag-to-place backend
      (`services/gateway` + `services/documents` + py-kit). BACKEND half done:
      the gateway `/{id}/export` + `/{id}/sheet` take an optional `sheet`
      query param (a sheet id from the tree; first sheet when omitted, back-compat;
      unknown id → `sheet_not_found` 404) threaded through
      `_aggregate_compose_request`/`_compose_request`, so the FINDINGS #18 switcher
      renders + exports ANY sheet. View-position persistence: new `auto_place`
      column (migration 0010, server-default true) + `ViewCreate/Update/Response`
      field; a PATCH `position` + `auto_place=false` persists a dragged view and
      survives reload, threaded into `SheetViewPlacement.auto_place` so compose
      honors it verbatim. `just gen`/`gen-check` clean; documents + gateway
      pytest + new regressions green. Frontend drag UI consumes this next.
      [src: FINDINGS.md #18 follow-up]
- [x] (P2, M) Multi-sheet drawings — FRONTEND half (`apps/web` + `packages/design`).
      Consumes the backend seam above: (1) compose/export follow the ACTIVE sheet —
      `composeDrawingSheet`/`exportDrawing` thread the switcher's sheet id as
      `?sheet=` (keyed on it so switching refetches), replacing the "managed
      secondary sheet" placeholder with a real compose. (2) Drag-to-place: a new
      instrument-grade blueprint-blue view-frame + corner grip on the sheet lets a
      view be dragged (or arrow-key nudged) to author its centre, persisted via
      `PATCH …/views/{id}` (`updateView`, `auto_place:false`, screen→y-up flip) so
      it survives reload; an "AUTO" control returns the view to auto-layout. New
      `drawing.placement*` tokens; SVG export strips the placement chrome. web unit
      820 + design 46 green; e2e drawing-place-view (active-sheet compose +
      drag-persist) + drawing-sheets + drawings green; founder shots
      `drawing-place-view-*` + `drawing-active-sheet-compose-1440`.
      [src: FINDINGS.md #18 follow-up]
- [x] (P2, M) Audit G2 — per-request work bounds (rate limiter caps frequency,
      not cost). Documented schema constants → typed 422s: deflection floors
      1e-3 mm / 1e-2 rad; pattern count ≤ 500 (+ kernel guard); features ≤
      1000; assembly instances/mates ≤ 500/2000; interference ≤ 200 instances
      (N², typed handler 422); drawing views/dims/notes ≤ 32/500/500; sketch
      entities/constraints ≤ 2000/4000; loft ≤ 100; selector refs ≤ 500.
      documents write-side `*_limit_exceeded` twins. 42 new tests.
      [src: AUDIT-ENGINEERING.md 2026-07-24 G2]
- [x] (P0, M) Fail closed on default datastore credentials (publishing
      blocker). `loft_env` hoisted into py-kit `BaseServiceSettings` (one
      posture field for all three services; `gateway.auth.security` now reads
      `py_kit.is_dev_env`) + one inherited `model_validator`: a publicly-known
      default or blank password in `POSTGRES_URL`/`REDIS_URL`/`S3_URL`, or in
      geometry's `S3_SECRET_ACCESS_KEY` (via `datastore_credential_fields`),
      refuses to boot unless `LOFT_ENV=dev`, where it warns. Error names the
      variable, the compose knob, and the fix. Compose passes `LOFT_ENV` to
      all three; `.env.example` gap paragraph rewritten. 48 tests, each branch
      mutation-verified. [src: cb0dcd0 follow-up / AUDIT-ENGINEERING J4]
- [x] (P1, S) Compose audit fixes G1/G3/G4 — geometry S3 creds anchor-sourced
      from MinIO's (G1); documents/geometry host ports removed from base compose,
      loopback-bound in dev overlay (G3); stale S3 comment rewritten (G4); new
      `scripts/check-compose.py` invariant guard in CI compose job.
      [src: AUDIT-ENGINEERING.md 2026-07-24]

### Recently shipped (2026-07-23 batch)

- [x] (P2, S) Revolve construction-centerline axis closes an open half-profile
      (`build_revolve_profile_face`; new `revolve-centerline-cylinder-r12-h20`
      golden V=2880π; annulus golden byte-identical). Web follow-up: revolve
      editor axis-pick should allow construction lines. [src: product-auditor]
- [x] (P1, M) Assembly interference/collision detection. `POST /api/v1/assembly/
      interference` (geometry) + auth'd/rate-limited gateway proxy; reuses
      `EvaluateAssemblyRequest`, adds `InterferenceResult`/`ClashPair`. Reuses
      `solve_assembly` (shared solve → world-placed kernel bodies), places each
      body via the shared `kernel/export.place_body` transform, pairwise
      `BRepAlgoAPI_Common` (`kernel/interference.intersection_volume`, GProp
      volume) → `clashes: [{instance_a, instance_b, overlap_volume_mm3}]` (each
      unordered pair once). Principled volume floor = one kernel-tolerance cube
      (1e-12 mm³): coincident-face touch ⇒ no clash. N² over bodied instances =
      accepted v1 bound (broad-phase AABB pre-filter = additive v2). Gates: 6
      worked tests — empty/non-overlapping, analytic 2500 mm³ overlap (measured
      2499.99999999999955, err 4.5e-13, rel-tol 1e-6), repeated-part single-pair,
      just-touching zero-volume no-clash, HTTP route. Never-500 (typed status +
      clash list). [src: AUDIT-PRODUCT.md 2026-07-23]
- [x] (P0, M) Assembly STEP export — AP214 product structure. `POST /api/v1/
      assembly/export` (geometry) + auth'd/rate-limited gateway proxy;
      `ExportAssemblyRequest` (shared DTO = evaluate fields + export format).
      `solve_assembly` factored out of `evaluate_assembly` so export reuses the
      identical solve → placed kernel bodies; `assembly/export.py` composes them
      through build123d's XCAF `STEPCAFControl_Writer` (each instance a named
      PRODUCT at its solved world placement; STL = one baked compound).
      Byte-deterministic (pinned STEP timestamp + kernel-side canonicalisation of
      the process-global NAUO occurrence-id counter). Gates: worked
      export→`import_step`→placement round-trip (world mass-props within the
      kernel round-trip bound), PRODUCT-name traceability, in-process + across-
      restart determinism, body-less→422 `assembly_export_no_body`, over the two
      bolted goldens; single-part `/export` untouched.
      axis-aligned-offset datum) — `drawings/section.py` half-space cut + exact
      coplanar loops (`BRepTools_WireExplorer`, exact corners) + `ComposedHatch`
      (ANSI-45° even-odd scanline clip) across SVG/PDF/DXF; `views.section_params`
      jsonb (0008). Independent code-review + geometry-QA caught a wrong-half bug
      (front/XZ section keyed removal off `plane.z_dir` not the eye normal) — fixed
      `57dca7a`: removal single-sourced through `view_normal(view)`; adversarial
      suite (14 tests, 0 xfail) + full sweep green (lint + geometry + e2e 191).
      Oblique + `project_view` frame refactor are v2/§11. [src: drawings pillar;
      AUDIT-PRODUCT; GEOMETRY-QA 2026-07-23]
- [x] (P1, S) Drawings D1 (export + DOM) — title-block author/date/notes now
      stamped in SVG/PDF/DXF and on-screen. [src: AUDIT-ENGINEERING.md D1]
- [x] (P2, S) Drawings D2 — authored `DimensionPlacement` (offset/text_pos) now
      honored by the composer. [src: AUDIT-ENGINEERING.md D2]
- [x] (P2, S) Drawings D3 — `first_angle` projection wired (ISO 128 view swap).
      [src: AUDIT-ENGINEERING.md D3]
- [x] (P2, S) Drawings D4 — assembly-kind views typed-422-gated instead of an
      opaque downstream 404. [src: AUDIT-ENGINEERING.md D4]
- [x] (P2, M) Engineering audit — DEAD-CAPABILITY systematic sweep: 6 orphaned/
      half-wired drawing capabilities found + verdicted (D1-D6). [src: WB-64 retro]
- [x] (P2, S) Drawing export DE-4 — content-addressed drawing-artifact cache
      (SVG/PDF/DXF) on the mesh_store/S3 seam. [src: drawing-export.md §8.3]
- [x] (P2, S) Drawings — note annotations render end-to-end (export SVG/PDF/DXF
      + DOM + authoring panel); fixed a real gateway gap (annotations never
      threaded to compose). [src: founder dogfooding — WB-64]
- [x] (P3, S) Drawings — auto-layout sheet-SIZE control (A4→A0+ANSI); fit-scale
      now respects the chosen sheet. [src: founder dogfooding — WB-64]
- [x] (P2, S) MB-4c tail (wire + frontend) — per-body lump count on the evaluate
      wire + Bodies-panel "N solids" badge. [src: MB-4c honest wire gap]
- [x] (P1, S) e2e — 6 raster-fragile specs fixed (root cause: stale pre-units
      format string, not raster drift) + 1 real ≤2px band-fit tolerance. [src:
      orchestrator bisect]
- [x] (P2, S) e2e — heavy founder-flow specs hardened against CPU contention
      (explicit 30s solve/eval waits). [src: orchestrator]
- [x] (P0, M) Sheet metal WF-1 — cut-after-fold fold-back invariant (layer 1) +
      edge-flange WIDTH EXTENTS/auto bend-end relief/partial-width flat pattern
      (layer 2, design §4.5); PB-1 fell out of the same machinery. [src: founder
      dogfooding — WF-1/PB-1]
- [x] (P2, S) Sheet metal — width-extents EDITOR UI (Full/Centered/Offset +
      in-scene span preview). [src: founder dogfooding — WF-1]
- [x] (P2, M) Sheet metal — hem on a FLANGE top edge now flat-patterns
      (topological flank resolution + fold-provenance return partitioning).
      [src: founder dogfooding — TB-1]
- [x] (P2, S) Sheet metal — CornerReliefEditor in-scene Bend A/B highlight +
      edit-mode guards (SM-relief-ui-1). [src: docs/UI-REVIEW.md 2026-07-19]
- [x] (P1, S) Drawings — incumbent-parity matrix (`drawings-parity.md`, sourced
      SolidWorks/Fusion) + 12-item ordered campaign. [src: founder dogfooding —
      WB-64 + retro]

### Sheet metal v1/v2 + corner relief + hem + STEP hardening (2026-07-19)

- [x] (P1, M) Sheet metal — closed-hem + corner-relief authoring UI
      (HemEditor + CornerReliefEditor). [src: design/sheet-metal-parity.md §2/§3]
- [x] (P1, M) Sheet metal — FULL 4-CORNER PAN corner relief (shared-flange +
      late-flange fold-back fixes). [src: design/sheet-metal.md §4.4.4]
- [x] (P2, S) Sheet metal — CLOSED HEM feature (180° fold, reuses edge-flange
      machinery). [src: design/sheet-metal-parity.md §2]
- [x] (P2, M) Sheet metal — CORNER RELIEF v1 geometry + fold-back
      cross-consistency gate. [src: design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal — CORNER RELIEF wired as an authorable feature. [src:
      design/sheet-metal.md §4.4]
- [x] (P2, M) Sheet metal v2 #2 — depth-≥2 bend-TREE unfold feature (box
      corner/return/Z). [src: design/sheet-metal.md §4.3, §10]
- [x] (P2, M) Sheet metal v2 spike — bend-chain depth-≥2 tractability proof
      (TRACTABLE, recursive tree walk). [src: design/sheet-metal.md §10]
- [x] (P2, M) Sheet metal v2 #1 — non-parallel depth-1 bend stars (2D
      plus/cross layout). [src: design/sheet-metal.md §4.3]
- [x] (P2, S) STEP import — parse-timeout hardened against CPU-contention
      (`RLIMIT_CPU` + wall-clock liveness backstop). [src: code-reviewer]

### Phase 0 (through commit 322a988)

- [x] (P1, M) Monorepo scaffold — uv + pnpm workspaces, justfile, lint/test
      gates green. [src: roadmap]
- [x] (P1, M) `packages/py-kit` service bootstrap — config, JSON logging,
      app factory, error envelope, queue client; unit tested. [src: roadmap]
- [x] (P1, L) Service skeletons + compose — gateway/geometry/documents on
      py-kit; parameterized Dockerfile + compose stack config-validated;
      smoke + dev-instance scripts (runtime `up` = blocked item above).
      [src: roadmap]
- [x] (P1, M) Contract pipeline — `just gen` + `just gen-check` drift gate;
      OpenAPI → `packages/contracts` → `packages/ts-client`. [src: roadmap]
- [x] (P1, L) Web shell + first light — design tokens (`packages/design`),
      r3f viewport rendering OCCT-tessellated GLB via the gateway, live
      parametric editing, Playwright e2e, founder screenshots.
      [src: roadmap, founder]
- [x] (P1, M) CI pipeline — lint/typecheck/unit, contract drift, compose
      validation as four parallel GitHub Actions jobs. [src: roadmap]
- [x] (P2, M) Geometry golden harness — data-driven golden runner + STEP
      round-trip gate; cube golden at 0.0 measured deviation; evidence in
      docs/GEOMETRY-QA.md. [src: roadmap]
- [x] (P2, S) Community surface — truth-only README, CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, issue/PR templates. [src: roadmap]
- [x] (P0, batch) Phase 0 review-fix batch — geometry image runtime libs,
      pytest exit-5 gate, OpenAPI dedupe helper, readyz detail hygiene,
      corrupt-GLB surfacing. [src: code-reviewer]

### Phase 1 (through commit ff6b226)

- [x] (P1, M) STEP/STL export endpoints + UI download, first curved golden,
      feature-tree persistence design doc, `SketchSolver`+planegcs adoption,
      auth v1 (backend+web), documents parts CRUD, `just e2e` wiring.
      [src: roadmap, geometry-qa]
- [x] (P1, M) Feature-tree persistence (documents API + geometry evaluate
      slice), sketch model + solver API, sketcher UI (plane/entity authoring
      + constraints/solve feedback), extrude (add/cut) end-to-end.
      [src: roadmap]
- [x] (P1, M) Gateway mesh-fetch proxy, viewport renders evaluated bodies,
      extrude UI + feature-tree edit/rollback, parts home UI, fillet,
      chamfer, export-from-tree, full-flow Playwright exit gate.
      [src: roadmap, product-auditor, engineering-auditor]

### Phase 2 (through commit a1c42be) — parametric core converges

**Batch 1** (topological-naming design doc, construction geometry,
tangent/perpendicular/parallel + equal/symmetric/concentric constraints,
revolve, measurement tool, linear/circular pattern) through commit `5777656`.
**Batch 2** (fillet/chamfer authoring UI, sketch trim/extend/offset/mirror/
fillet-chamfer, splines v1, sweep, loft) through commit `1e3d422`. **Batch 3**
(offset/datum planes, multi-loop closed profiles → holes) through commit
`a36e436`. **Batch 4** (sketch-on-a-model-face, click-specific edge selection,
shell, draft — **Part modeling flips ➖→✅**; circular-pattern determinism
golden; STEP import v1 kernel-side; showcase stress test surfaces F1–F3;
pattern-a-cut + multi-disjoint-loop cut close F1/F2) through commit `d8d3b87`.
**Batch 5 — Phase 2 converges** (through `36dc3d9`): STEP import P1 security
+ gateway upload + UI file-picker (**Interop flips ❌→➖**); typed
over-constraint diagnosis (#6); sketch dimension expressions + driving/driven;
constrainable spline fit points v1.1 (backend+frontend) — **Sketching flips
➖→✅** (`a1c42be`); gateway auth-gate on geometry-compute routes (audit F7 P1
security, `36dc3d9`); assemblies architecture decision endorsed (`b378633`);
both audits re-baselined 2026-07-15. Full per-item evidence: `CHANGELOG.md`.

### Phase 3–4b (through `a6a5814`, 2026-07-15 to 2026-07-19)

Full evidence lives in `CHANGELOG.md`'s "Phase 3" + "Phase 4a" +
"Phase 3+4a+4b" sections (backfilled this pass) and the design docs cited.

- [x] Assemblies v1 — document model, `AssemblySolver` (numpy-only, no GPL,
      quaternion 6-DOF + closed-form fast path), mate-geometry resolution,
      evaluation + shared-mesh tessellation, gateway, frontend workspace +
      mate authoring; distance/angle mates; flat BOM + panel. **VISION
      ❌→➖.** [src: design/assemblies.md]
- [x] Drawings v1 — document model, exact-HLR projection, evaluate endpoint,
      gateway proxy, frontend sheet editor, dimension measurement/provenance
      + authoring (linear/diameter/radius/angular/point-to-point), SVG
      export. **VISION ❌→➖.** [src: design/drawings.md]
- [x] Drawing export DE-0…DE-3 — server-composed placement (`ComposedSheet`,
      one placement source), reportlab PDF + ezdxf DXF serializers, gateway
      export proxy, frontend Export PDF/DXF controls, client placement
      engine deleted. [src: design/drawing-export.md]
- [x] Multi-body modeling + booleans v1 — MB-0…MB-4c: a part can end with
      >1 body; union/subtract/intersect between independently-built bodies;
      downstream fillet on a boolean-created edge; multi-lump bodies + opt-in
      disjoint union; multi-solid STEP import as one multi-lump body; frontend
      Combine editor + Bodies panel + guided `boolean_disjoint` recovery.
      geometry-QA PASS twice. [src: design/multi-body.md]
- [x] Sheet metal v1 — base flange, edge flange (+ `CylindricalFaceSignature`
      provenance, Spike 0 tractability proof first), depth-1-bend-star
      unfold, flat-pattern drawing view + bend table (server-composed,
      frontend-rendered), bend-table export-consistency fix, 120° regression
      golden. **VISION ❌→➖.** [src: design/sheet-metal.md]
- [x] Performance benchmark suite + CI tripwires — two-tier perf gate
      (`test_benchmarks.py`): generous asserted DoS/gross-regression ceilings
      (1000/2000 ms, 19×–435× warm) in the default suite + an opt-in
      `-m benchmark` median/p95 tier (`just bench`) that records the baseline
      table. Corpus = the shipped goldens (tree/boolean/tessellate/step/
      sheet-metal/drawing/assembly). Deliberately NOT a >10% CI bound (flakes
      under contention — moved to the human-watched tier). INFRA half of the
      Performance ❌ row only; the real-part corpus is still open, so no
      ❌→➖ flip. [src: geometry-qa gap #7; docs/GEOMETRY-QA.md 2026-07-19]
- [x] Units (length) v1 — `LengthUnit` on part/assembly documents; frontend
      convert/parse/format core threading every feature-param length input +
      the distance mate. [src: design/units.md]
- [x] Undo/redo v1 — server-side bounded snapshot rings (part + assembly),
      verbatim id-preserving restore, History command-band controls +
      keyboard shortcuts, `ToolButton` `aria-describedby` a11y fix folded in.
      [src: design/undo-redo.md]
- [x] Viewport makeover Batches 1–3 — full-bleed canvas + atmosphere + matcap
      shading + view rail (Batch 1); decorative-chrome deletion + gated tool
      reasons (Batch 2); in-command band depth + body hover/select feedback
      (Batch 3). Batch 3 remainder (per-face pick, ghost previews, resting
      datum sheets) stays open — see Next. [src: UI-REVIEW full audit]
- [x] Datum-plane completeness — midplane + offset-chaining kinds, backend +
      authoring UI. `on_face`/midplane-face-sides authoring + angled/
      3-point/tangent/normal-to-curve kinds stay open — see Ready/Later.
      [src: founder ask 2026-07-16]
- [x] Mesh-store MinIO/S3 swap (audit F1/F6), STEP re-parse cache (audit F8),
      Redis-backed rate limiting (audit F7 second half) — all three
      engineering-audit debt items closed. [src: engineering-auditor]

## Changelog

- 2026-08-08 — **SEL-6b a hidden body stops OFFERING picks too
  (frontend-builder):** `hiddenPicks.ts` withholds a switched-off body's edges,
  faces and snap points; 24 edge marks -> 12, 12 face marks -> 6, wall hidden.
- 2026-08-08 — **SEL-6 a hidden body stops eating the pick behind it
  (frontend-builder):** `pickRaycast.ts` filters hidden triangles inside
  `raycast`; shell reachability with the wall hidden 7.4 % -> 96.3 %.
- 2026-08-08 — **SEL-4 independent QA verdict: PASS (qa-tester):** 25 e2e green
  on the real stack, `e2e/qa-sel4-verify.spec.ts` adding the 10 checks the
  shipped gate did not express (draft, refusals, recede, mount audit, touch).
- 2026-08-08 — **SEL-4 review follow-up 2026-08-08 (frontend-builder):** a
  hidden body stops occluding the edge band (`resolveBandIntersections` +
  `PickTriangle`); mate picks gated (8.9 % -> ≥50 %); one owner for mate hover.
- 2026-08-08 — **SEL-4 (5/5) the dense-hole gate A2 asked for
  (frontend-builder):** `seedDenseHolePlate` + `e2e/pick-affordance.spec.ts`,
  anisotropy not area for edges, mutation-verified on all three conversions.

- 2026-08-08 — **SEL-4 (4/5) drill anywhere on the face (frontend-builder):**
  free placement by raycast + plane projection; the snap nodes still win inside
  their 24 px because they are DOM above the canvas. Behaviour change.

- 2026-08-08 — **SEL-4 (3/5) shell, draft and mates address the geometry
  (frontend-builder):** surface raycast + edge band + the hover highlight
  neither had. Shell reachability measured 1.7 % -> 95.6 % of the lit body.

- 2026-08-08 — **SEL-4 (2/5) fillet/chamfer/measure pick the EDGE
  (frontend-builder):** a 24 px screen-space `LineSegments2` corridor with an
  occlusion test. Measured 13 px in every direction -> 40–130 px along.

- 2026-08-08 — **SEL-4 (1/5) one pick hit-test, shared (frontend-builder):**
  `PickSurface` / `FacePatch` / `useViewportPickStamp` / `edgeBand` (pure,
  unit-tested) extracted from `FacePickOverlay`, plus `sceneToOcctTuple`.

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
Entries before 2026-07-22 live in `CHANGELOG.md`.
