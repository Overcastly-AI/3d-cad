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

- **Groom pass 5 (2026-08-15 evening, this pass) — the founder's four
  2026-08-01 sketcher complaints all now have answers.** Dimensions assign
  (DIM-1, gate flipped, `a810524`+`810d9fb`); orbit-while-sketching reaches a
  trackpad (VP-1/VP-1a); a saved sketch re-opens (SKETCH-1); "snap points do
  not work" resolved through SNAP-1 -> SKETCH-2 -> the QA-SK2 follow-up fix
  (`8f00dec`) — detection was always correct, selection was not, and the
  frame no longer asks you to delete a constraint you cannot see. **New
  reading, sharper than the original report:** independent QA of SKETCH-2
  (`docs/UI-REVIEW.md` QA-SK2-4) found a snap to the origin/axis copies the
  COORDINATE but authors no constraint — the corner looks grounded, saves as
  "N applied," and then drifts on the first re-drive. Filed below (SNAP-2)
  as the sharpest open founder-adjacent defect, same silent-trust-violation
  class as DIM-1 was.
- **✅ rows, still qualified:** Sketching & constraints and Part modeling are
  creation- AND now datum-editing-capable (SKETCH-2), but still ➖-grade until
  PICK-1 (non-tip feature edits 422) and GEOM-3 (GEOM-2's honest limit on
  vented/perforated faces) land, and until SNAP-2 closes the silent-drift gap
  above. SKETCH-1/VP-1/VP-1a/DIM-1/SKETCH-2 are QA'd green but **none of the
  five have an independent `code-reviewer` pass** — flag this to the
  orchestrator; it is process debt, not a defect, but it is real debt.
- **Process note, not a scorecard row:** the CI-4 "systemically unstable e2e"
  umbrella got a substrate pass this session (`8d5be24`) — one of its two
  named failures (the camera-probe race) is root-caused and fixed with a
  0/12-after ablation; the other (`sketch-on-face` screenshot variants)
  could not be reproduced in 35 starved runs and stays filed, not fixed.
  **QAH-1 is CLOSED — `c3019b6`, an ANCESTOR of `a658db4` (verified:
  `git merge-base --is-ancestor c3019b6 a658db4` -> yes).** This groom pass
  first searched only `a658db4..HEAD` (the range the dispatch brief gave)
  and, finding nothing there, wrongly corrected the brief's "already shipped"
  claim to "still open" — a real error, caught by the orchestrator re-pointing
  at the right range, not by re-deriving harder inside the wrong one. `c3019b6`
  is a genuinely different fix from `8d5be24`'s camera-probe race (that
  distinction stands and is worth keeping apart): QAH-1 was a mutation-test
  constant — `diagnostics.ts:193`, `rendersInProbeWindow: … ? null : 0, //
  MUTANT: always 0` — left in the tree by `0580f7d`'s reconciliation of a
  stopped agent's work, whose own e2e gate was never run. See the archived
  entry for the evidence.
- **➖ rows (usable, short of incumbent parity):** Assemblies (export +
  interference shipped; import, exploded views, recursive BOM, part-version
  pinning still missing). Interop (part STEP round-trips to 1e-9 against an
  independent OCCT re-read; assembly import still the gap). Drawings (auto
  re-projection + associativity genuinely good; the *printed sheet* still
  truncates the title in the export, prints 2 of 3 dimension texts over the
  part outline, and carries no part-no/rev/material/tolerance/projection-symbol
  fields — M13). Sheet metal (bend chains/corner relief/hems/edge-flange
  extents shipped; open/teardrop/rolled hems, miters, tabs, gauge tables
  still missing).
- **❌ rows:** Performance (`docs/PERF.md`, PERF-1..5 fixes shipped; no
  standing benchmark GATE yet — the row text overstates the gap per the fresh
  audit's M19 measurements, ~700-850ms full rebuild on an 11-feature part).
  Collaboration & versioning and Extensibility/scripting+MCP remain untouched
  (Phase 3 / Phase 5, unstarted).
- **`docs/COMPETITIVE.md`** still dates from 2026-07-19 — stale against every
  finding above; flagged again for the vision-steward to refresh. Ready queue
  restocked from the fresh BACKLOG-native audit findings this pass.

## Ready (top of queue)

**Dispatch order, this pass — PICK-1 and GEOM-3 have sat Ready longest of the
P0s without being dispatched; nothing has overtaken them, but the order
between them is worth stating.** GEOM-3 should go FIRST: it is a SILENT
wrong-geometry defect (a deleted-feature's sketch can re-target onto the
wrong face with no error at all), which is the class CLAUDE.md ranks above
everything else on the board, including PICK-1. PICK-1 fails LOUDLY (a 422)
rather than silently, which is the less dangerous failure mode even though it
fully blocks a whole class of edits (M9/M10) — a real product/scorecard hit,
just not a "wrong answer accepted as right" one. SNAP-2 (new this pass) is
comparable in shape to PICK-1 — correct now, silently wrong after a later
edit — but shares `apps/web/src/sketch/**` territory with nothing else
currently Ready, so it can run alongside GEOM-3 (kernel-architect territory)
without contention; PICK-1 and SNAP-2 do NOT share territory either
(`PartPage.tsx`/editor components vs. `sketch/store.ts`/`snap.ts`) so up to
three of GEOM-3/PICK-1/SNAP-2 can be dispatched in parallel this batch.
QAH-1 (CI-reliability debt) is CLOSED as of this pass — see Done archive.

- [ ] (P1, S) **DIM-3 — the Dimension verb's ARMED state (c449235) is
      invisible, and a wrong-kind pick prints the exact sentence the arm-fix
      exists to eliminate** (`apps/web/src/sketch/store.ts`). Two related
      defects found reviewing c449235. (a) armed state is surfaced ONLY
      through `hint`, and two ordinary actions null the hint while leaving the
      verb armed — `selectConstraint` (`store.ts:1305`) and `togglePick`
      (`store.ts:909`) — so the next canvas click can open a dimension editor
      with no visible cause. (b) a wrong-kind pick while armed (e.g. a circle
      under Distance) prints `"Select one line to dimension."` (`store.ts:
      890-895`) — the exact pre-fix refusal sentence, and FALSE while armed
      (the user clicked, they did not select — "select" describes the OLD
      selection-first flow); the committed test enshrines this wrong string.
      FIX: (a) an armed-state affordance that survives `selectConstraint`/
      `togglePick` (don't null `hint` while `dimensionPick` is set, or add a
      dedicated indicator); (b) a wrong-kind message that doesn't reuse the
      refusal sentence, e.g. names the picked kind. ACCEPTANCE: (1) arm
      Dimension, call `selectConstraint`/`togglePick`, confirm the armed
      affordance still shows before the next click; (2) wrong-kind pick while
      armed shows a message that is not "Select one line to dimension." and
      stays armed; new/updated `store.test.ts` cases for both. Mutation check:
      reverting either half reddens its own assertion only.
      [src: code review of c449235, orchestrator dispatch 2026-08-14]
      TERRITORY: `apps/web/src/sketch/store.ts`,
      `apps/web/src/sketch/store.test.ts`. agentType: frontend-builder.

- [ ] (P1, S) **ESC-2 — two implementations of the Escape cascade disagree
      about SAVE vs DISCARD for the same rung, kept apart only by an omitted
      default argument — a latent FB-13 landmine.** `PartPage.tsx:1046`
      re-derives the cascade with its own `escapeAction(...)` call, mapping
      `"exit"` to `finishSketch()` (SAVES); `store.ts:1467` maps the SAME verb
      to `freshSession()` (DISCARDS). They cannot disagree TODAY only because
      `PartPage.tsx` omits `escapeAction`'s 5th argument, so `unstarted`
      defaults false and `"exit"` is unreachable there — `finishSketch()` at
      that call site is dead code. This is exactly the "a key that sometimes
      saves and sometimes discards" defect CLAUDE.md's flow mandate names
      (FB-13's class), lying dormant: any future change that makes `unstarted`
      reachable from `PartPage.tsx` reintroduces FB-13 silently, because the
      two cascades are two separate implementations. FIX (DRY — CLAUDE.md
      non-negotiable): ONE cascade, owned by `sketch/store.ts` (already
      exercised by tests); `PartPage.tsx` calls it instead of re-deriving
      `escapeAction`. ACCEPTANCE: `PartPage.tsx`'s escape handling calls the
      SAME function `store.ts` uses; a new test exercises the `"exit"` rung
      reachable from `PartPage.tsx`'s entry point (armed pick, empty/unstarted
      sketch) and asserts it DISCARDS, matching `store.ts`'s existing
      semantics. Mutation check: reintroducing a second independent mapping
      reddens the new test.
      [src: code review of c449235, orchestrator dispatch 2026-08-14]
      TERRITORY: `apps/web/src/routes/PartPage.tsx`,
      `apps/web/src/sketch/store.ts`. agentType: frontend-builder.

- [ ] (P0, M) **PICK-1 (M16) — a viewport pick is stamped with the TIP
      feature's id, not the feature that owns the sub-shape, so no non-tip
      feature can ever be re-picked for an edit** (`apps/web/src/routes/
      PartPage.tsx`, `apps/web/src/components/{FilletEditor,ChamferEditor,
      ShellEditor,DraftEditor,EdgeFlangeEditor,HemEditor}.tsx`). Root cause of
      M9/M10 (a picked-edge fillet's radius can NEVER be edited, failed or
      not — `PATCH` 422s `reference_not_earlier` naming the fillet's OWN id)
      and a contributor to M17. Confirmed in source:
      `bodyFeatureId` (`PartPage.tsx:1430`, comment: "the last body-affecting
      feature") is computed ONCE as the current TIP and threaded unmodified
      into every fillet/chamfer/shell/draft/edge-flange/hem editor
      (`PartPage.tsx:4118-4198`), which use it to build every
      `SubshapeRef.feature_id` (`faceSubshapeRef`/`edgeSubshapeRef` in
      `features/{face,edge}.ts`). That is correct when CREATING a new feature
      (the pick necessarily belongs to the current tip) but wrong when
      EDITING an existing one: the edge you re-pick belongs to whatever
      feature actually produced it, which the backend correctly rejects as
      "must come strictly earlier" when it turns out to be the tip (or the
      feature under edit itself). The data needed already exists server-side:
      `OverlayFace.feature_id` (`services/geometry/src/geometry/kernel/
      overlay.py:87-149`) is set from face provenance already (FINDINGS #9,
      feature-localized selection). INVESTIGATE first whether that per-face
      `feature_id` already reaches the frontend's pick payload (it may only be
      used for hover tooltips today) — if not, thread it through the overlay
      fetch into the pick handler. Then: when a pick happens during an EDIT
      session (as opposed to a fresh create), resolve the `SubshapeRef`'s
      `feature_id` from the picked geometry's own owning feature, not from
      `bodyFeatureId`. ACCEPTANCE: reproduce M10 first as the control (create
      a 3-edge fillet R4, re-open it, change radius to R3 — today this 422s
      naming the fillet's own id); after the fix the edit succeeds and volume
      changes to the new closed-form value. New e2e spec covering: (a) edit a
      picked-edge fillet's radius, (b) edit a picked-face shell's thickness,
      both against a body with ≥2 features between the picked feature and the
      tip. Mutation check: reverting the resolution (back to `bodyFeatureId`
      everywhere) must redden both.
      [src: product-auditor pass 2026-08-14 (M9, M10, M16)]
      TERRITORY: `apps/web/src/routes/PartPage.tsx`,
      `apps/web/src/components/{Fillet,Chamfer,Shell,Draft,EdgeFlange,Hem}
      Editor.tsx`, `apps/web/src/features/{face,edge,modify,shell,draft,
      sheetMetal}.ts`, `services/geometry/src/geometry/kernel/overlay.py`
      (if the per-face id needs threading through), new e2e spec.
      agentType: frontend-builder (cross-check overlay wiring with
      kernel-architect if the geometry-service response needs a field added).

- [ ] (P0, M) **GEOM-3 — GEOM-2's honest limit now has a number, and on an
      ordinary vented/lightened part it is closer than §12a's qualitative
      caveat suggested.** Code review of `8b95dac`/tier 4 (`enclosing_face_match`,
      `geometry.kernel.faces`) derived the exact admission rule: tier 4 accepts
      any stored face whose relative area `f` satisfies **`f >= 1 - 2r`**, where
      `r` is the candidate face's open-area fraction. At r=10% the smallest
      wrong face admitted is 80% of the outer region; r=25% -> 50%; r=37.5% ->
      25%; at r>=50% tier 4 degrades to normal-sense + containment alone —
      exactly as §12a's prose already warned, now with the threshold attached.
      MEASURED (not extrapolated) on a **100x100 vented plate, 8x8 grid of Ø9
      through-holes** (r=40.7%, "an ordinary grille or lightened web"):
      `outer=10000.0 current=5928.5 removed_frac=0.407 lower_bound=1857.0`.
      Deleting the boss a sketch sits on and re-evaluating: a 70x70 boss top
      (4900 mm², tier4=True) RESOLVES onto the plate underneath; 60x60
      (3600 mm²) RESOLVES; 50x50 (2500 mm²) RESOLVES; only 40x40 (1600 mm²,
      tier4=False) stays an honest error. That is guard 2's own designed
      failure case — the boss-deletion scenario tier 4's lower bound exists to
      keep an HONEST error — now firing on a boss covering a QUARTER of an
      ordinary perforated plate, not a pathological one. For scale, the M17
      bracket itself is r=17.7% (lower bound 65% of the plate): comfortably
      safe; the cliff is real but not universal. Does NOT argue for reverting
      GEOM-2 — the alternative is a P0 that strands features on every
      multi-feature face — this is the case FOR the durable fix flagged (and
      deliberately deferred) at ship time, see the GEOM-2 entry in the Done
      archive: `PlanarFaceSignature`
      (`packages/py-kit`) should store outer-boundary invariants instead of
      `area_mm2` + area centroid, removing the need to infer a bound from three
      numbers at all. NOTE the ordering: that contract change ALSO needs tier 4
      for every selector authored before it, so `8b95dac` is its prerequisite,
      not a workaround — do not skip straight to the contract change.
      ACCEPTANCE: `PlanarFaceSignature` carries an outer-boundary invariant
      (e.g. outer wire signature/hash, not area+centroid alone); tier 4 (or its
      successor) resolves the vented-plate boss-deletion case correctly (stays
      an honest error at every boss size up to the full 70x70, not just
      <=40x40); the M17 bracket golden and all tier-4 goldens stay green;
      new golden(s) at r>=25% covering the boss-deletion honest-error case.
      Mutation check: reverting the outer-boundary storage back to area+centroid
      reddens the new r=40.7% golden.
      [src: code review of 8b95dac, relayed 2026-08-15 — not yet committed to
      docs/GEOMETRY-QA.md or the design doc; whoever picks this up should land
      the inequality and the vented-plate measurement there too]
      TERRITORY: `packages/py-kit/**` (PlanarFaceSignature schema),
      `services/geometry/src/geometry/kernel/faces.py` (tier 4 and its
      successor), `docs/design/topological-naming.md` §12a, geometry goldens.
      agentType: kernel-architect.

- [ ] (P0, M) **SNAP-2 — a snap to the origin/axis copies the COORDINATE but
      authors no CONSTRAINT, so a grounded-looking sketch silently drifts on
      its first re-drive.** Found by independent QA of SKETCH-2 (`docs/
      UI-REVIEW.md` QA-SK2-4, `c82ff09`), confirmed against the real solver.
      Draw a rect with its first corner SNAPPED to the origin: the marker
      reads `origin`, the DRO reads `+0.00 / +0.00`, the strip reads "9
      applied" — and there is **no `origin` entity and no constraint naming
      it**. Re-drive a width 30 -> 40 and the part slides to **x = -7.1716
      mm**; a genuinely grounded twin (corner joined with `c`) re-driven
      40 -> 55 stays at exactly (0,0). QA's words: "there is no signal in
      between — the mark looks identical, the count is identical, nothing
      marks the corner." Same defect CLASS as DIM-1 before its fix (the tool
      appears to have understood you and has not) but a different SEVERITY
      profile, worth stating plainly rather than inheriting DIM-1's tier by
      default: the geometry recorded at save time is exactly what was typed/
      snapped — nothing is wrong YET — the wrongness is deferred to a LATER
      edit, the same shape as PICK-1 (M9/M10) and GEOM-3, which is why this is
      filed at their tier rather than DIM-1's "wrong the instant you look."
      MECHANISM: `placeAt(point: Point2D)` (`apps/web/src/sketch/store.ts:805`)
      receives only the resolved coordinate; the `SnapCandidate` already on
      `resolution.candidate` (`apps/web/src/sketch/snap.ts:84-97`) carries
      `entities: readonly string[]` — the exact id(s) an inferred coincident
      needs — and nothing reads them at placement time. Fusion and SolidWorks
      author that inferred constraint on snap; this is the gap between "aim
      lands exactly on the target" (true here) and "stays attached" (false).
      FIX: when `placeAt` resolves via an `origin`/`x-axis`/`y-axis`/endpoint/
      midpoint snap (not the grid or a free point), author the matching
      coincident (or on-axis) constraint against `resolution.candidate.
      entities` at the same commit that adds the drawn entity — mirroring how
      the drag-release gesture and the rigidity-set-on-first-dimension already
      inject constraints alongside geometry. Needs a product decision on
      SCOPE: infer for ALL entity-snap kinds (endpoint/midpoint too, closing a
      second, older reading of "snap points don't work" — the corner separates
      from its neighbour on edit) or just the datum frame (narrower, faster,
      directly closes QA-SK2-4). Recommend shipping the datum-frame case first
      (this ticket) and filing the general entity-snap case separately once
      shipped, rather than blocking on the larger design. ACCEPTANCE: draw a
      rect with a corner snapped to the origin, save, re-drive the width — the
      corner stays at exactly (0,0), matching the `c`-grounded case; a new e2e
      spec proves it, and a companion asserts the OLD behaviour (coordinate
      copy, no constraint) is what's being replaced, i.e. the spec must fail
      on current HEAD. Mutation check: skipping the inferred-constraint
      authoring reddens the new spec's re-drive assertion only.
      [src: independent QA of SKETCH-2, `docs/UI-REVIEW.md` QA-SK2-4,
      2026-08-15]
      TERRITORY: `apps/web/src/sketch/store.ts` (`placeAt`), `apps/web/src/
      sketch/snap.ts`, `apps/web/src/sketch/datum.ts`, new e2e spec. Same
      territory as SKETCH-2/the hydration-guard item below — do not run
      concurrently with either. agentType: frontend-builder.

- [ ] (P0, M) **FB-21 — the origin axis glyphs are labelled in KERNEL space but
      drawn in SCENE space, which the GLB rotation has already turned.**
      Founder: *"check the axis. Turn on the axis and compare them to the view
      cube."* MEASURED: kernel +Z maps to scene +Y (glTF node rotation
      `[-0.7071,0,0,0.7071]`, a -90° turn about X, baked into the merged
      mesh buffer), but `OriginGeometry.AXIS_DIRECTION` draws the Z glyph at
      scene `[0,0,1]` — an unrotated identity — so the glyph labelled Z points
      where the kernel's -Y actually lives, and the part's true height (kernel
      +Z) runs along the glyph labelled Y. `Viewport.tsx`'s `upFor()` (Y-up
      camera convention) compounds it: the ViewCube's TOP looks down the
      part's true height while the Z axis glyph points sideways. NOT yet
      established: whether `sketch/plane.ts`'s plane bases are un-rotated the
      same way (if so, plane glyphs mislead identically — settle by
      rendering + comparing against a body of known dimensions, not by
      reading source). Do NOT fix by swapping label constants blind — decide
      ONE stated frame convention first, verify by screenshot against the
      ViewCube, THEN make axis glyph / plane glyph / ViewCube / model agree.
      ACCEPTANCE: one documented frame convention; a gate asserting the
      labelled Z glyph is parallel to the extrude direction of an XY sketch.
      [src: founder 2026-08-02, still open]
      TERRITORY: `apps/web/src/viewport/OriginGeometry.tsx` (or equivalent),
      `apps/web/src/sketch/plane.ts`, `apps/web/src/viewport/Viewport.tsx`
      (camera `upFor`). agentType: frontend-builder.

- [ ] (P0, S) **FB-9 — "the extruded is not on the same plane"** (photographed
      by the founder, still open; POSSIBLY the same root cause as FB-21's
      kernel/scene frame mismatch above — check that first before treating as
      a separate bug). Original repro steps and photo evidence: see git
      history / prior BACKLOG text (`git log -S"FB-9"`) if not reproducible
      from the description alone. ACCEPTANCE: reproduce on current HEAD (frame
      convention may have already shifted since this was filed); if it shares
      FB-21's cause, close as a duplicate once FB-21 lands and this case is
      re-verified fixed; if independent, root-cause and fix separately with a
      gate.
      [src: founder, still open — re-verify against current HEAD before
      assuming FB-21 is the same bug]
      TERRITORY: TBD by reproduction — likely `apps/web/src/viewport/**` or
      `apps/web/src/sketch/plane.ts`. agentType: frontend-builder.

## Next (P2)

- [ ] (P2, S) **SKETCH-3 — reserved-id hydration guard: an externally-authored
      entity named `origin`/`x-axis`/`y-axis` would silently BECOME the sketch
      frame.** Named and deliberately NOT built by the SKETCH-2 builder, with
      reasoning worth preserving rather than re-litigating: `withoutDatums`
      (`apps/web/src/sketch/datum.ts:182`) is id-based, so a foreign entity
      sharing one of the three reserved ids would be hidden from drawing and
      picking, and `groundDatums` (`datum.ts:237`) would pin it as though it
      were the real frame. A correct fix is not cheap — renaming on hydration
      risks references the client cannot enumerate (constraints, drawing
      views, mate authoring all cite entity ids by string), and a warning that
      only announces the collision without resolving it is decoration, not a
      fix. Exposure is THEORETICAL today: nothing external authors sketch JSON
      — Phase 5's scripting/MCP surface is the first path that would. FIX:
      once Phase 5 lands a write surface, either namespace the reserved ids
      out of the user-authorable range (e.g. a sigil no client-authored id can
      produce) or validate + reject/rename on ingest with full reference
      remapping. ACCEPTANCE: a hydration test that constructs a sketch with a
      user entity literally named `origin` and asserts the frame is NOT
      silently replaced (exact behaviour — reject vs. remap — is a product
      decision to make when this is picked up, not implied by this ticket).
      [src: SKETCH-2 builder, flagged not built, relayed by groomer 2026-08-15]
      TERRITORY: `apps/web/src/sketch/datum.ts`, sketch persistence/hydration
      path. agentType: frontend-builder. Gate on Phase 5 scripting surface
      landing; do not build ahead of the exposure that makes it real.

- [ ] (P1, XS) **FB-19b — FB-19 shipped (`f7c41d9`) but is not DONE: unreviewed,
      unQA'd, and the founder has not seen the before/after screenshots.**
      The chrome-density fix (label-beside-control `FieldRow` primitive,
      compacted `NumberField`/`SelectField`/`Checkbox`/`SegmentedControl`,
      measured origin block 212.0px->95.0px, extrude card 368.3px->219.5px,
      tree panel 591.0px->474.0px, all against stated ceilings) is preserved
      and gate-passing at the unit level only (typecheck, 1618 web + 86 design
      unit tests, prettier/eslint clean) — the agent died before its own
      `fb19-chrome-density.spec.ts` e2e gate ran even once, and no
      `code-reviewer`/`qa-tester` pass has happened. ACCEPTANCE: (1) run
      `fb19-chrome-density.spec.ts`, root-cause and fix if red; (2)
      `code-reviewer` + `qa-tester` sign off; (3) orchestrator SENDS
      `docs/screenshots/fb19-*` to the founder in chat per CLAUDE.md's design
      mandate ("surfaced" = sent, not merely generated) — this last step is
      not a build task, flag it for the orchestrator rather than a builder.
      [src: FB-19 provenance note, groomed 2026-08-15]
      TERRITORY: read-only verification; `apps/web/e2e/
      fb19-chrome-density.spec.ts` only if it needs a fix. agentType:
      frontend-builder or qa-tester.

- [ ] (P1, M) **FOUNDER — no Fusion-style hover-a-face-to-sketch.** Founder
      complaint: today, starting a sketch requires clicking the Sketch
      command FIRST, then picking a plane/face; Fusion lets you hover an
      empty-context face and click a glow-in affordance to sketch on it
      directly, no prior command needed. Related to M4(a) (product-audit pass
      2026-08-14): after a sketch is solved, the tool never proposes
      "Extrude this" either — both are instances of the same flow principle
      (CLAUDE.md design mandate: "the tool proposes, the user disposes").
      Scope this item to the HOVER-TO-SKETCH half only (the extrude-proposal
      half is a separate, larger item — see the FLOW-1 flow umbrella below).
      MECHANISM: when no command is active and the body is interactive
      (`mode === "off"`, per `PartPage.tsx`'s `bodyInteractive` computation),
      hovering a face should show a small in-viewport sketch affordance (icon
      or highlight) near the cursor; clicking it calls the same
      `handleNewSketch` + face-plane-authoring path the toolbar Sketch command
      already uses (`authorFacePlane`, `PartPage.tsx:3260+`), pre-seeded with
      the hovered face. ACCEPTANCE: hover a face with no command active — an
      affordance appears within N px of the cursor; click it — a sketch opens
      on that face's plane with the same behaviour as Sketch → pick that face
      today (byte-identical resulting plane/params). New e2e spec.
      [src: founder report 2026-08-14, needs UX detail decided by builder;
      cross-ref product-auditor M4(a)]
      TERRITORY: `apps/web/src/routes/PartPage.tsx`,
      `apps/web/src/viewport/**` (hover affordance rendering), new e2e spec.
      agentType: frontend-builder. DEMOTED from Ready 2026-08-14 (queue-thinning
      groom pass — pure flow polish, no correctness defect, not yet dispatched).

- [ ] (P2, XS) **ESC-3 — the one scenario where c449235's Escape-disarm rung
      actually prevents an exit (armed Dimension in an EMPTY sketch) is
      covered by no test, unit or e2e.** The shipped `store.test.ts` "Escape
      disarms it and does NOT exit the sketch" asserts `mode === "draw"`,
      which passes even with the rung ABLATED, because with 4 entities in the
      sketch the `unstarted` branch is unreachable — a tautology w.r.t. the
      fix under test. MEASURED by ablation: armed with 4 entities and the rung
      removed, Escape leaves `mode: "draw"` (existing test stays green); armed
      with ZERO entities and the rung removed, Escape gives `mode: "off"` —
      the sketch is gone. FIX: add a test that arms Dimension in an EMPTY
      sketch and asserts Escape disarms without exiting; keep the 4-entity
      test as a secondary regression, not the only one. Mutation check:
      reverting the disarm rung reddens the NEW empty-sketch test.
      [src: code review of c449235, orchestrator dispatch 2026-08-14]
      TERRITORY: `apps/web/src/sketch/store.test.ts`. agentType: frontend-builder.

- [ ] (P2, S) **VP-1b — orbit-while-sketching is undiscoverable; neither VP-1's
      MIDDLE button nor VP-1a's Alt+drag is announced anywhere in the
      sketcher.** `NavCue` (`apps/web/src/components/NavCue.tsx`) renders only
      when `viewNav` is true, which is false while sketching, and its copy
      ("Drag orbits") would be wrong there anyway (LEFT is reserved for
      drawing). FIX: a sketch-mode variant naming the two real bindings
      (MIDDLE-drag rotates; Alt/Option+drag rotates). Note TOUCH remains
      uncovered separately (a touchscreen has neither a middle button nor a
      modifier key) — file separately if this item doesn't absorb it.
      ACCEPTANCE: entering sketch draw mode shows a cue naming both bindings;
      test asserts the cue text differs from the non-sketch `viewNav` cue.
      [src: VP-1a follow-up noted 2026-08-14, filed this pass]
      TERRITORY: `apps/web/src/components/NavCue.tsx`,
      `apps/web/src/viewport/**` (wiring). agentType: frontend-builder.

- [ ] (P2, XS) **QA7-1b — the static gate QA7-1 shipped (`db144d7`) recognises
      a SOLVE-cell subject only via the literal `"eval-status"` string or a
      `const <name> = page.getByTestId("eval-status")` binding, so
      `page.locator("[data-testid=eval-status]")` or `const cell = status`
      slip past it undetected.** Measured by the reviewer: each shape applied
      then reverted, 1 passed — the gate does not fire. Neither shape exists in
      `qa-sel7-verify.spec.ts` today, so nothing is unguarded right now, but
      the gate's own header claims a completeness the code does not meet —
      this repo's own guard-encodes-the-direction-of-its-defect pattern.
      Separately, the gate is scoped to one file rather than all of
      `apps/web/e2e` (sibling specs were other agents' territory when it
      shipped). FIX: widen the binding-recognition regex to cover
      `page.locator`/arbitrary-identifier forms, and either promote the
      scanner to cover every e2e spec or lift it into a standalone
      `just lint`-wired script (`scripts/`) so new specs inherit the guard
      without a per-file copy. ACCEPTANCE: the two measured-slip shapes now
      fail the gate when they name a string outside `solveSummary`'s
      vocabulary; the non-vacuity negative control (the shipped pre-fix defect
      line, asserted before the subject) still passes.
      [src: code review of QA7-1 (`07c4005`), amber follow-up, filed 2026-08-15]
      TERRITORY: `apps/web/e2e/qa-sel7-verify.spec.ts` (scanner function),
      or a new `scripts/` gate if promoted repo-wide. agentType:
      frontend-builder.

- [ ] (P2, S) **TOUCH-1 — there is no touch/mobile Playwright PROJECT, and has
      never been one since `playwright.config.ts` was introduced; QA briefs
      that say "desktop AND touch" have been silently half-satisfied for the
      life of the e2e suite.** `apps/web/playwright.config.ts` declares a
      single default (desktop Chromium, 1600x1000, `deviceScaleFactor: 1`) —
      no `projects` array, so there is no systematic touch/mobile run of any
      kind. The only touch coverage that exists is ad hoc: 6 spec files
      (`qa-sel4-verify`, `qa-sel6-verify`, `qa-sel7-verify`,
      `measure-pattern-qa`, `full-flow`, `import-remix`) locally override
      `test.use({ hasTouch: true, viewport: … })` inside one describe block
      each — a hand-picked subset, not a run of the suite. This is a PROCESS
      defect as much as a coverage gap: any brief (including this repo's own
      QA dispatches) that asks for "desktop and touch" verification cannot be
      honoured by "run the touch project," because none exists — it can only
      mean "if one of these 6 specs happens to cover it." FIX: add a `projects`
      array with at least one touch-emulating profile
      (`{ ...devices["iPad (gen 7) landscape"], hasTouch: true }` or similar)
      that runs a deliberately-scoped touch SMOKE subset (not the full 350+
      spec suite doubled — sizing that subset is part of the work), wired into
      `e2e.yml` as its own shard/job so a touch regression has somewhere to
      show up. ACCEPTANCE: a touch project exists and runs in CI; at least the
      6 specs above (already touch-aware) run under it rather than only under
      per-spec overrides; document in this file's own convention (or
      CLAUDE.md) what "desktop and touch" verification means going forward so
      future briefs stop overclaiming coverage that isn't there.
      [src: QA finding, relayed 2026-08-15 — process gap, not a single bug]
      TERRITORY: `apps/web/playwright.config.ts`, `.github/workflows/e2e.yml`.
      agentType: platform-builder or frontend-builder.

- [ ] (P2, S) **TOUCH-2 — the sketch origin/frame grab disc is well under any
      touch-target guideline: 9 px at the default camera, 4 px zoomed out 32
      notches.** Measured by independent QA of SKETCH-2 (`c82ff09`,
      `docs/UI-REVIEW.md`). Related to TOUCH-1 (no touch Playwright project
      exists to have caught this) but a distinct product concern — the mouse
      pick tolerance (`PICK_TOLERANCE_PX = 8`) the ring rides on is well below
      WCAG 2.5.8's 24 px minimum, and unlike a drawn line a datum pin has no
      alternate keyboard-reachable affordance advertised anywhere in the UI
      (the SKETCH-2 QA found the keyboard Tab-to-origin path exists but
      undiscoverable). FIX: give the frame's hit region a touch-specific
      floor independent of the mouse pick tolerance (mirrors A7/SEL-1's
      existing pattern of a generous invisible hit area with a tighter visual
      mark). ACCEPTANCE: a touch-emulated pick (once TOUCH-1's project
      exists) hits the origin/axis at >=24 px from centre at the default
      camera; a unit test on the hit-region math independent of a touch
      harness in the meantime. [src: independent QA of SKETCH-2, `docs/
      UI-REVIEW.md`, 2026-08-15]
      TERRITORY: `apps/web/src/sketch/datum.ts`, `apps/web/src/sketch/
      origin.ts`. agentType: frontend-builder. Natural pairing with TOUCH-1;
      does not require it to ship first (the hit-region fix is independent of
      whether CI runs a touch project).

- [ ] (P2, XS) **QA-SK2-3 — "Finish sketch" silently drops a click landing
      during a live save, 2 in 10 under load.** `SketchStrip.tsx` disables the
      Finish button `disabled={saving || …}` for the duration of every
      constraint-edit's autosave; a click in that window is delivered to a
      disabled button and does nothing, with no feedback — measured always at
      `DOF 0 · CONVERGED`, i.e. the save had already succeeded. Pre-existing
      (not introduced by SKETCH-2), but SKETCH-2 put grounding-then-finish on
      the hot path so it is hit more often now. FIX: don't disable across a
      live save (it's already committed server-side), or queue the click and
      replay it when the save settles. ACCEPTANCE: a spec that triggers a
      save-in-flight and clicks Finish during it asserts the sketch exits
      (not silently ignored); reproduces the 2-in-10 rate before the fix,
      0-in-N after over a comparable number of trials.
      [src: independent QA of SKETCH-2, `docs/UI-REVIEW.md` QA-SK2-3,
      2026-08-15]
      TERRITORY: `apps/web/src/components/SketchStrip.tsx` (or equivalent),
      `apps/web/src/sketch/store.ts` (`finishSketch`). agentType:
      frontend-builder.

- [ ] (P2, S) **SPEC-6 — `measureReach` in `pick-affordance.spec.ts` reads
      `data-edge-pick-hover` with the same zero-settle pattern SPEC-5 found
      and fixed for the hole scan's `data-hole-point-hover` — filed, not
      fixed, and possibly already covered.** `measureReach` (`pick-affordance
      .spec.ts:150`) does `page.mouse.move(...)` then immediately
      `viewport.getAttribute(attribute)` with no wait for the React commit —
      the exact shape SPEC-5 (`c7d3f2a`) diagnosed and fixed at the hole-point
      call site, using an oracle that nulls the stamp against a known-off-body
      position first so a lag can't masquerade as a fresh read. Here the
      failure direction is the opposite of SPEC-5's (which under-read "on
      face"): a lagging read on `measureReach` INFLATES perpendicular reach
      against the fillet/measure/mate `<= 16 px` ceilings it feeds, i.e. it
      fails SAFE (hides a defect rather than reporting a false one) — which is
      exactly why nobody has been forced to notice yet. **CHECK FIRST**: a
      builder was live sweeping this file for zero-settle attribute reads as
      of this pass; before building a fix, confirm `measureReach` isn't
      already covered by that sweep. ACCEPTANCE (if not already covered):
      apply the same oracle pattern to `measureReach`'s attribute read;
      re-measure the currently-green reach thresholds this call site feeds
      (fillet/measure/mate specs) and confirm they don't move, or update them
      with the corrected (smaller) measured reach if they do.
      [src: ROADMAP CI-4 substrate pass, `8d5be24`/`c7d3f2a`, relayed
      2026-08-15]
      TERRITORY: `apps/web/e2e/pick-affordance.spec.ts` (`measureReach`).
      agentType: frontend-builder. DO NOT dispatch concurrently with any
      other agent already in this file — check git log / ask the orchestrator
      first.

- [ ] (P3, XS) **SPEC-7 — one observation, not a diagnosis:
      `pick-affordance.spec.ts:780` ("SEL-6 — the default face hover sees
      past a hidden body too") failed once on CI at `8d5be24`, with both
      immediate descendant commits green.** Filed as a single data point per
      this repo's own rule against diagnosing load-dependent failures from
      few samples — the orchestrator has been wrong twice this session doing
      exactly that. No cause is claimed. **CHECK FIRST**: a builder was live
      sweeping this same file for zero-settle attribute reads as of this
      pass (see SPEC-6); this single failure may already be explained or
      fixed by that work — read `git log` for `pick-affordance.spec.ts`
      before treating this as open. If still unexplained after that check:
      re-run the test under load a handful of times and see whether it
      reproduces before spending more on it; one CI sample with two green
      descendants is not yet evidence of a standing defect.
      [src: orchestrator CI observation, relayed 2026-08-15]
      TERRITORY: `apps/web/e2e/pick-affordance.spec.ts`. agentType:
      frontend-builder or qa-tester (reproduction first, before any fix).

- [x] (P1, S) **K7 — Stop hook in-flight guard fixed. SHIPPED 29387da
      2026-08-14.** Depth-agnostic `find -path '*/tasks/*.output' -mmin -30`,
      `-print -quit` (the piped `grep -q` form was also wrong under
      `pipefail`), `--self-test` against a harness-produced fixture with 4
      negative controls. [src: engineering-auditor pass 5, 2026-08-14 (K7)]

- [ ] (P2, S) **K2 — no route-sweep authn gate exists; the gateway's
      unauthenticated surface has grown from 71 to 87 routes in two weeks with
      nothing to catch a new route shipping without `CurrentUser`**
      (`services/gateway/tests`). Posture is correct TODAY (swept by hand:
      only `/auth/{login,register}` + the 3 infra probes are unauth'd; 60/64
      documents routes carry `owner_id`) but nothing enforces it going
      forward. NOTE for whoever builds this: FastAPI 0.139 no longer flattens
      included routers into `app.routes` (`_IncludedRouter` wraps them) — a
      naive walk sees ~3 routes and reads as "nothing to check"; recurse
      through `_IncludedRouter.original_router.routes`. Gate must carry a
      COUNT FLOOR (`all([])` over 3 infra routes is vacuously true — the
      repo's recurring gate-cannot-fail shape).
      [src: engineering-auditor pass 5, 2026-08-14 (K2); was J7, 2026-07-30]

- [ ] (P2, S) **K3 — no automated licence gate over the ~1,036-package npm
      tree; `check-licences.py` covers the Python environment only**
      (`.github/workflows/ci.yml`, `scripts/`). `docs/LICENSING.md` §5's JS
      table (78 prod packages, all MIT/Apache/ISC/OFL/BSD/Unlicense) was
      produced by a human running `pnpm licenses list` once on 2026-07-31; a
      GPL npm package added tomorrow fails no gate anywhere. Given this repo's
      P0 licence incident (LIC-1) was caused by exactly this — trusting a
      one-time human read of dependency metadata — close the asymmetry:
      `pnpm licenses list --prod --json` piped through an allowlist, ~15
      lines, in the `licences` CI job beside the Python profile.
      [src: engineering-auditor pass 5, 2026-08-14 (K3)]

- [ ] (P3, XS) **K6-tail — derive `docs/ROADMAP.md`'s "Current focus" line
      instead of hand-writing it; this is the THIRD time an audit has found it
      stale (H6 2026-07-25, J13 2026-07-30, K6 2026-08-14).** Fixed by hand
      again this pass. Recommend a machine-written line (newest non-docs-only
      commit's ticket prefix, or a `docs/.last-sweep` record) so it cannot
      drift between grooms. Low priority precisely because it costs nothing to
      keep fixing by hand each pass — but three recurrences says the field
      itself is the bug.
      [src: engineering-auditor pass 5, 2026-08-14 (K6)]

- [ ] (P2, S) **K8 — three of the last five commits landed with no
      independent code review and no QA pass, disclosed only in the commit
      message, not in ROADMAP or BACKLOG** (process). `d091112` (FB-20),
      `a2bb859` (CI-3), `0580f7d` (REV-1d) — reconciliation of a stopped
      agent's work is the right call per RETRO §1.2, but the debt needs to be
      VISIBLE where the groomer reads, not just in `git log`. Convention going
      forward: an `(UNREVIEWED)` suffix on the BACKLOG line (now applied to
      FB-20/CI-3 in the archive above) until code-reviewer + qa-tester have
      independently passed it. Also noted: BACKLOG had exactly one
      `CLOSED-PENDING-QA` marker while RETRO §6.5 said "several" — fix
      whichever is wrong when next touching RETRO.
      [src: engineering-auditor pass 5, 2026-08-14 (K8)]

- [ ] (P2, XS) **REV-1(c) — `qa-harness.spec.ts:730` asserts a tautology:
      `/achieved 0 render\(s\)/` can only fire when `observed < 1`, so the
      match is guaranteed by construction after a non-throwing call. Same at
      :704-706 for three other asserted values.** Sub-items (a)(b)(d)(e)(f)(g)
      of the original REV-1 are CLOSED — see `docs/ROADMAP.md`'s 2026-08-14
      entries for the measurements. Only (c) remains: replace the tautological
      regex assertions with a check that could actually fail (e.g. assert the
      SPECIFIC render count, not merely "not zero").
      [src: ultracode review 2026-08-13; groomer-compacted 2026-08-14]

- [ ] (P2, XS) **REV-2 — the retries posture guard stops covering a renamed
      Playwright config, silently** (`.github/workflows/e2e.yml:380`). Filed
      2026-08-13; PROVEN BY EXECUTION in the review. `grep ... || true` absorbs
      grep's exit 2 (no such file) as well as exit 1 (no match), so renaming
      `apps/web/playwright.config.ts` to `.mts` — which Playwright still
      auto-discovers — with `retries: 2` injected prints
      `posture: no retries, --fail-on-flaky intact` and exits 0. The only trace
      is one swallowed stderr line. Exactly the "enumerated gate that quietly
      stops covering" shape the same file's prose condemns 200 lines above.
      Not higher priority because `--fail-on-flaky` remains a genuine
      independent backstop: a retry that actually FIRES still reddens the
      reconcile job. It is the posture CLAIM that is falsifiable-in-name-only.
      FIX (3 lines, before the greps): assert each file the guard enumerates
      exists, and fail naming it when it does not.
      [src: ultracode review, 2026-08-13]

- [ ] (P2, S) **REV-5 — the two instruments that could close the stale-readback
      and context-loss exposures are exercised only by themselves**
      (`apps/web`). Filed 2026-08-13.
      (a) `requireRenders` — the strict mode `de3755f` shipped precisely to stop
      a census sampling a stale buffer — has ZERO product consumers. All three
      call sites are in `qa-harness.spec.ts`, the gate that tests it. Note the
      review's warning before wiring it in: `waitForRenders` counts renders
      since the WAIT starts, so `requireRenders: true` at a census site throws
      whenever the render already landed, which is the common case. Wiring it up
      needs a different shape, not a flag flip.
      (b) `qa-harness.spec.ts:756` asserts `glEvents` is EMPTY, i.e. that the
      `webglcontextrestored` path was never taken — so the `invalidate()` fix at
      `Viewport.tsx:505`, sold as a real product fix, is exercised by nothing.
      `WEBGL_lose_context` is available in headless Chromium, so the mutation is
      cheap: lose, restore, assert the scene repaints with no user input, and
      assert it FAILS with the `invalidate()` removed.
      [src: ultracode review, 2026-08-13]

- [ ] (P1, M) **CI-4 — the e2e suite has gone systemically unstable: THREE
      mechanisms in FOUR consecutive runs, so no commit's CI signal can be
      trusted right now** (`apps/web`, `.github/workflows`). Filed 2026-08-11 by
      the orchestrator. This is the umbrella over CI-3 and SPEC-3; it outranks
      both, because the rule "every commit green on its own" is unenforceable
      while the suite fails for a different reason every other run.
      THE BOARD: `45c8592` FAIL, `7ffac16` PASS, `aea990a` FAIL, `688539d` PASS,
      `c6b6c6d` FAIL. Always exactly ONE spec of 115-116, never the same one.
      (a) `45c8592` — `interaction-depth.spec.ts:40`, colour count 316 vs > 336;
      the ghost's raster-independent marker PASSED (see SPEC-3).
      (b) `aea990a` — `sketch-drag-draw.spec.ts:258`, dying in `createPartViaApi`
      with `502 upstream_unavailable / reason: ReadError`, on a commit holding
      only a python script and `CLAUDE.md` (see CI-3).
      (c) `c6b6c6d` — `sketch-visibility.spec.ts:164`, `countTokenPixels(page,
      "#E9F1F8")` = ZERO against a floor of 120. Qualitatively different from a
      thin margin: no scribe pixels at all. The `frame.pxPerMm < 40` assertion
      immediately above it passed, so the frame WAS fitted.
      WHY AN UMBRELLA AND NOT THREE SPEC PATCHES: three unrelated assertions
      failing one-at-a-time across consecutive runs, including on a commit whose
      diff cannot reach the app, is the signature of a shared substrate problem
      — most likely resource pressure on the runner over a ~12 min shard —
      rather than three independent spec bugs. Patching each assertion would
      raise the pass rate while leaving the cause, which is the outcome this
      repo's "no hand-waving" rule exists to prevent.
      FIRST MOVES, in order: (1) instrument rather than guess — have the shard
      record wall-clock, RSS and CPU alongside each spec, and capture the three
      services' logs as artifacts on failure (the gateway log would settle CI-3
      immediately); (2) check whether failures cluster late in a shard;
      (3) `sketch-visibility` ink = 0 must be reproduced LOCALLY at HEAD before
      being called environmental — SEL-6 changed `pickSurface.tsx` and
      `ModelMesh.tsx`, so a real sketch-on-face rendering regression is NOT ruled
      out by CI alone, even though `7ffac16` and `688539d` (both carrying SEL-6)
      ran that spec green.
      DO NOT "fix" this by adding Playwright retries: `e2e complete` runs
      `--fail-on-flaky` deliberately, and a retry would convert a real
      intermittent product defect (CI-3 is one) into a green board.
      PLATFORM SLICE SHIPPED 2026-08-11 (this commit) — move (1) and (2) are
      done and the no-retry posture is now enforced by the workflow: service
      logs survive the run (`E2E_LOG_DIR`, uploaded `if: always()`, tailed into
      the job log on a red — the trap used to delete them before upload), a 2 s
      resource sampler runs on green and red alike, `e2e-shard-audit.py
      --timeline` prints where in the shard each test ran, and the verdict step
      greps for retries. STILL OPEN: CI-3's gateway fix.
      Re-derive shard ordinals per-SHA; the suite is 467 tests today.
      FRONTEND SLICE SHIPPED 2026-08-11 (this commit) — F1/F2 landed and move
      (3) is DONE: `waitForFrames` counted browser animation frames against a
      silent 2 s valve while the viewport is `frameloop="demand"` (an idle page
      ticks 92 frames in 1.5 s with ZERO renders), so it now waits on a real
      r3f render counter and THROWS with the count achieved; every non-passing
      test attaches the viewport readback + substrate. And ink = 0 REPRODUCES
      locally at HEAD (5 of 10 runs) with the ink plainly on screen at 0.74
      coverage — an anti-aliasing phase lottery in the census, not a rendering
      regression, and not the runner. See SPEC-4.
      **SUBSTRATE PASS 2026-08-15 (`8d5be24`) — one of the suite's two named
      failures root-caused and fixed, the other filed honestly unreproduced.**
      `cameraPose: no camera captured` (`sketch-orbit.spec.ts`) was the probe
      reading the camera before the demand-mode scene had rendered even once;
      it now polls rAF-paced with a bounded deadline and names which of three
      causes it's in on timeout. Ablation: 2/4 pass under 6 CPU hogs before,
      6/6 after. The `sketch-on-face` screenshot-variant failure could NOT be
      reproduced in ~35 starved local runs across six load-generation methods;
      three candidate shared mechanisms with the camera-probe fix were each
      ruled out by instrumentation (not argument), so it stays filed rather
      than force-unified. Separately, `pick-affordance.spec.ts`'s hole-scan
      read a React-state attribute with zero settle after `page.mouse.move`
      and produced a false accusation of DIM-1 (`a810524`) before being
      root-caused and fixed (`c7d3f2a`, SPEC-5) — see the note on
      `measureReach`'s sibling exposure, filed separately below. NOT the same
      ticket as QAH-1 (`qa-harness.spec.ts`, "renders while orbiting") —
      different assertion, different mechanism, and QAH-1 was already CLOSED
      before this substrate pass (`c3019b6`, an ancestor of `a658db4` outside
      the window this pass first searched — see Done archive).
      [src: orchestrator CI root-cause, 2026-08-11; substrate pass 2026-08-15]

- [x] (P2, XS) **CI-2 — `deploy-path` never got the per-SHA concurrency fix, so
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
      SHIPPED 2076de4. Recurred and was re-measured before the fix: `8d386ab`
      came back `cancelled` on deploy-path on 2026-08-14 while the six commits
      either side succeeded — **81 s wall clock (13:27:33 -> 13:28:54) and
      `total_jobs: 0`**, against a 45-minute ceiling. Zero jobs is the decisive
      discriminator: an eviction kills a PENDING run before any job exists,
      whereas a `timeout-minutes` kill requires a job to have started and
      reached its limit. So there is no second bug hiding behind the word
      "cancelled" here.
      The builder REFUSED to take the orchestrator's eviction diagnosis on
      trust — it cannot read CI — and recorded the observation in the workflow
      file with its evidentiary status ("the reason somebody looked, not the
      proof"), resting the change on the mechanism instead. The orchestrator
      then fetched the per-job breakdown above. That is the right shape and is
      worth copying.
      It also priced the trade honestly and found a SECOND cost the ticket did
      not name: ref-keying was *serialising* the image builds, so per-SHA means
      up to 8 concurrent deploy-path jobs under four pushing agents, on top of
      ci's 6 and e2e's 5. Judgement recorded in-file that the trade is still
      right — a serialised gate that discards evidence is not cheaper, it is
      unpaid — and that if runner contention bites, the lever is the TRIGGER
      (`paths-ignore`), never the key.
      GATE: `scripts/check-workflow-concurrency.py`, wired into `just lint` and
      ci.yml's `compose` job, stdlib-only, ~60 ms. It derives coverage from the
      filesystem (every workflow with a push trigger), so a workflow added
      tomorrow is covered and no list can go stale. Verified by the orchestrator
      against the REAL pre-fix file, not a fixture: `git checkout HEAD~1 --
      .github/workflows/deploy-path.yml` makes it exit 1 naming
      `deploy-path-${{ github.ref }}`. `--self-test` carries 8 fixtures of which
      5 MUST fail, including **arms swapped** (PR keyed on sha, push on ref) —
      the symmetric mistake a check that merely grepped for `github.sha` would
      sail past, which is this repo's own
      guard-encodes-the-direction-of-its-defect lesson applied in advance. It
      also cross-checks its own line reader against PyYAML and REFUSES to report
      on disagreement, with a negative control on the refusal itself.
      NOT verified: no image was built (registry 403), and the acceptance
      criterion above — two back-to-back pushes each completing — can only be
      observed on the next real double push.

- [ ] (P0, L) **FB-8 — "too many [points] to see what you are clicking"; wants
      Fusion/Plasticity pre-selection** — a snapping pointer, the FACE (not the
      body) highlighting under the cursor, and a small axis showing direction.
      `ModelMesh.tsx:37` types highlight as per-BODY (`"none" | "hover" |
      "selected" | "feature"`), so hovering glows the whole solid. This is the
      root of FB-2/FB-3 as EXPERIENCED: a mis-aim is invisible instead of visible
      and free. The hovered-face normal also pre-empts FB-4 — you would see which
      way "out" points before authoring. Spec IN FLIGHT (vision-steward).
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
- [ ] (P0, L) **FLOW-1 (was FB-20 — renumbered 2026-08-14, id collided with the
      camera-stolen-after-extrude fix also called FB-20, `d091112`; see the
      archive) — the FLOW from sketch to feature, and the parts page, both need
      an overhaul.** Founder: "we need to fine tune the flow from
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
      UPDATE 2026-08-14: sliced. The sketch->feature half is now three
      concrete Ready items — SKETCH-1 (sketch re-open), PICK-1 (pick-stamped-
      with-tip root cause), VP-1 (orbit while sketching) — plus DRAG-1 below
      (hover-normal arrow, a direction control, NOT yet the full draggable-
      distance handle M5 asks for — that remains open). Fresh audit
      confirmation (product-auditor pass 2026-08-14): M4 measures the "no
      proposal after a solved sketch" and "camera stays normal-on through the
      extrude preview" halves precisely; M5 re-confirms zero manipulator DOM
      exists anywhere (fillet/shell/hole depth too, not just extrude); M18
      finds no orthographic mode and a ViewCube that does not snap to the face
      clicked. This item stays open as the umbrella/parts-page tracker; treat
      the slices as the actual buildable work.
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

- [ ] (P1, M) **DRAG-1 — hovered-face normal arrow, doubling as the extrude/cut
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
      NOTE 2026-08-14: id renamed from a stale SEL-4 collision (SEL-4 now
      names the shipped edge/shell/draft pick fix). This is a DIRECTION
      control (forward/reverse arrow), not the draggable-DISTANCE handle
      the founder's #1 gap (M5, product-audit 2026-08-14) asks for — both
      are needed; M5 is the bigger one and is unclaimed.

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
- [ ] (P2, S) Drawings — PROCESS GUARD: a non-default-value compose golden per
      optional authored field. **Nearly closed** — title-block (D1), first-angle
      (D3), and dimension-placement (D2) goldens all landed this batch; only the
      D5 orientation (portrait) golden remains once D5 authoring ships. [src:
      AUDIT-ENGINEERING.md cross-cutting]
- [ ] (P2, S) Assembly export — persistent ROTATED multi-instance golden under
      `goldens-assembly/`. Both shipped export goldens
      (`assembly-two-plates-bolted`, `assembly-two-plates-gap`) solve every
      instance to IDENTITY orientation, so the `gp_Quaternion` placement path is
      only guarded by a synthetic test (`test_step_assembly_export_nonidentity_
      rotation_roundtrip`, added by geometry-QA 2026-07-23). Lock a 3-instance /
      repeated-part / non-identity-rotation assembly as a committed golden so the
      "green suite, wrong rotated geometry" hazard is a permanent gate, not a
      synthetic one. [src: GEOMETRY-QA.md 2026-07-23 assembly-export QA]
- [ ] (P1, M) **MB-HOLE — Hole only ever drills the ACTIVE body, while the face
      pick offers every body's faces, so a hole on any earlier body dies at
      Create with `HOLE_OFF_BODY`** (`services/geometry`, `apps/web`). Found
      2026-08-11 by qa-tester while verifying SEL-7 on the two-body
      `seedBoredPlateAndBlock` fixture; NOT a SEL-7 regression — measured with
      the body drawn and hidden, identical either way. MEASURED, three runs, same
      face each time (`plane-pick-face-4`, the plate's top at OCCT 30, 30, 10):
      one-body dense plate -> **Solved**, volume 34 020.8 -> 33 738.05 mm³
      (Δ 282.7 = Ø6 x 10); the SAME plate as body 1 of a two-body part ->
      **Failed / HOLE_OFF_BODY**, volume unchanged at 38 020.8; the second body's
      own top face -> **Solved**, 38 020.8 -> 37 738.05. The plate's BOTTOM face
      fails too, so it is the BODY that is unreachable, not a face-normal case.
      Mechanism (read-only): `evaluate.py:_hole` drills `state.active_body`, and a
      `merge: false` extrude makes the NEW body active — every modifying feature
      inherits this, so Fillet/Chamfer/Shell on an earlier body are very likely
      the same defect and should be measured in the same pass. FLOW: the pick
      offers a target the command cannot act on, and the refusal arrives only
      AFTER Create, as a red tree row ("no dead ends, no ambiguous exits").
      FIX candidates: derive the target body from the picked FACE rather than
      from `active_body_id`, or withhold the faces of non-active bodies in the
      pick (worse — it makes the model invisible instead of wrong). ACCEPTANCE: a
      hole placed on any body's face drills THAT body; e2e on the two-body
      fixture asserting Solved + the Δ-volume for a hole on body 1.
      [src: qa-tester, SEL-7 verification 2026-08-11]

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
- [ ] (P2, S) **GEOM-4 — tier 4's containment check leaves a derivable
      constraint unenforced: when a stored face's area equals the outer
      region's, its centroid MUST equal the outer region's centroid.**
      `outer·C_outer = stored·C_stored + removed·C_removed` implies this
      directly, but `enclosing_face_match` only tests containment. MEASURED
      accepting a bogus signature: a plain 100x40 face with `area_mm2 = 4000`
      (== outer) and `centroid = (5, 3, 10)` returns `enclosing_face_match ==
      True`. Would NOT have caught GEOM-3's vented-plate case (boss and plate
      share a centroid there), and no shipped test currently depends on it —
      a strengthening opportunity, not a live defect. FIX: when `stored ==
      outer` (within tolerance), assert `centroid == outer_centroid` as an
      additional necessary condition before accepting the match. ACCEPTANCE:
      the bogus-centroid case above is REFUSED; every existing tier-4 golden
      stays green (their centroids already satisfy the identity, since they
      came from a real subtraction). Small enough to ride with GEOM-3 if that
      lands first, or standalone otherwise.
      [src: code review of 8b95dac, relayed 2026-08-15]
      TERRITORY: `services/geometry/src/geometry/kernel/faces.py`
      (`enclosing_face_match`). agentType: kernel-architect.
- [ ] (P3, XS) **GEOM-5 — an unlisted honest limit for §12a: a hole enlarged
      until it BREACHES the outer boundary (a scallop or edge slot) changes
      the outer wire itself, which is the one invariant tier 4 rests on.**
      Fails SAFE (the outer region shrinks and the upper bound refuses) but is
      the most likely real edit that defeats the claimed invariant, and
      deserves a line in the doc beside the already-documented concave-face
      and grown-face limits. Doc-only; no code change implied.
      [src: code review of 8b95dac, relayed 2026-08-15]
      TERRITORY: `docs/design/topological-naming.md` §12a — land alongside
      whoever next touches GEOM-3/GEOM-4 rather than as a standalone dispatch.
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

- [ ] (P3, XS) **REV-3 — FB-7's collapsed rail tab aligns to the wrong edge on
      the RIGHT rail** (`apps/web/components/FloatingPanel.tsx:94-95`). Filed
      2026-08-13; MEASURED in Chromium against the repo's real Tailwind build.
      `railed ? "shrink-0 self-start"` has no side branch, unlike every other
      side-aware clause in the file. At 1280x650 with a 320px card docked above:
      rail `right=1268`, tab `right=1049.8` — 218 px of empty column to the
      right of a tab on a `right-3`-anchored rail, and a behaviour change from
      the floating case, which pinned it to `right-3`. Reachable in the shipped
      flow: `HoleEditor` is unconditionally `seat="right"` and the inspector is
      mounted during hole editing.
      FIX: `railed ? cx("shrink-0", side === "right" ? "self-end" : "self-start")`.
      Cosmetic — the tab stays visible and clickable — but one line, and it sits
      in the flow FB-7 exists to fix. Also note (a) of the same lens: collapsing
      the inspector leaves ~91 px of measured dead column; worth a note, not a
      restructure.
      [src: ultracode review, 2026-08-13]

- [ ] (P3, S) **REV-4 — six more untrue statements in comments and docs, plus
      two dead code paths** (`apps/web`, `scripts`). Filed 2026-08-13 from the
      review's claims audit. Each is small; batched so they are fixed once.
      (a) `support.ts:550-552` — "NEVER SLOWER THAN ITS PREDECESSOR" is false and
      self-contradicting two clauses later. The predecessor raced n rAFs against
      a 2 s timeout; the successor has a 15 s ceiling and no shortcut. MEASURED:
      `waitForFrames(page, 30)` took **2317.7 ms** in a quiet window. Correct
      form: never waits fewer FRAMES; wall clock can be longer, by design.
      (b) `ChromeRail.tsx:53-59` — the stated reason for context-over-ref is
      wrong in both halves: the shipped `useState`+`useEffect` path is ALSO null
      on first commit, and a plain ref would float forever, not "for one frame".
      The code is right; the reason is not.
      (c) `support.ts:292` — constants "exported so a spec can state what it
      calibrated against"; no spec imports them and the calibration comment
      never names 0.25 or 24.
      (d) `e2e-shard-audit.py` — the `"timedOut" in self.statuses` branch is dead
      (Playwright's JSON reporter serialises a timeout as `unexpected`, already
      covered); harmless, but say so or delete it.
      (e) `e2e-shard-audit.py` timeline — "N tests" / "% of the way through"
      counts only tests that RAN; skipped tests have `results: []` and vanish.
      (f) `e2e.yml:204` — "a job timeout kills the `if: always()` upload steps"
      is REASONING ONLY and unmeasurable from this container; GitHub documents
      `always()` as running on cancellation. The step-timeout change is right for
      its other stated reason, so nothing needs reverting — soften the sentence
      or check it against one real timed-out job.
      (g) `ChromeRail.test.tsx:54` — the second case's assertion is byte-identical
      to the first's and its title claims a `data-viewport-chrome` check it does
      not make. It can fail, so it is not dead; it adds zero coverage.
      [src: ultracode review, 2026-08-13]

- [ ] (P3, XS) **SPEC-3 — the live-extrude-ghost gate is a thin statistical
      margin, and it fails on framing rather than on the ghost** (`apps/web`).
      Filed 2026-08-11 by the orchestrator. `45c8592`'s e2e went red on
      `interaction-depth.spec.ts:40` at `Expected > 336, Received 316`; the
      assertion is `distinctCanvasColors(page) > inkColors + 8`.
      WHY THE GATE AND NOT THE FEATURE: the raster-INDEPENDENT hook asserted
      immediately above it — `extrude-preview-active` attached with
      `data-distance-mm="10"` — PASSED, so the ghost was present. The descendant
      `7ffac16` then ran the same spec GREEN on the same tree.
      WHY IT IS FRAGILE: `distinctCanvasColors` (`support.ts:345`) samples every
      16th pixel and counts distinct RGB, so it is an AA- and framing-sensitive
      statistic. The assertion is a NET — colours the ghost ADDS minus any the
      extrude editor REMOVES (sketch grid/plane) — and +8 is a thin margin on a
      difference. The spec's comment calls a bare sketch "relatively few shades"
      while the measured baseline was 328, so the premise no longer describes
      the scene it runs in.
      FIX: assert on something the ghost alone controls (its own pixels inside a
      known rect, or a token-coloured sample), or restate the floor around a
      margin measured across runs instead of a hardcoded +8. Same class as the
      CI-1 fix — pin the claim to hundreds-vs-zero, not to a framing-specific
      ratio.
      [src: orchestrator CI root-cause, 2026-08-11]

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

- [ ] (P2, S) **SEL-3 — stacked-candidate count badge** (`apps/web`). When
      `pickCandidates(...).length > 1` (sketch) or a raycast hit disagrees
      with a nearby armed-pick `PickNode` within tolerance, show a small `+N`
      badge beside the SEL-2 marker (reuses the app's one round-badge
      convention — no new tokens) so cycling is discoverable, not silent.
      Design + acceptance A4: `docs/design/pre-selection.md` §3, §6.
      [src: founder]

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

- [ ] (P3, L) **CONC-5 — OCP does not release the GIL, so one geometry worker
      can never use more than one core** (kernel, likely upstream). Measured at
      **1.05-1.15 cores** with 1/2/4/8 concurrent requests in flight and 11-18
      OS threads live; throughput is flat and latency linear in user count. Every
      other item above is a workaround for this. A `py::gil_scoped_release`
      around the long OCCT calls in OCP would make one worker use one machine;
      short of that, the per-core-worker rule in `docs/OPERATIONS.md` §6 stands.
      Filed at P3 because it is upstream work with a shipped workaround, not
      because it is small. [docs/PERF.md 2026-08-01]

- [ ] (P3, S) **CONC-7 — nobody sized the connection pools, and the defaults
      are wrong in the direction that hurts** (backend). Neither pool is
      configured: `py_kit.db` takes SQLAlchemy's default 5+10 connections per
      service process, and `create_upstream_client` takes httpx's default 100
      max connections to geometry — i.e. the gateway will pile 100 requests onto
      a worker with one effective core. Nothing exhausted during the 2026-08-01
      run, so this is not a live defect; it is an undocumented default that
      makes CONC-2 worse and belongs in `docs/OPERATIONS.md` §6 with a number
      behind it. [docs/PERF.md 2026-08-01]

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
- [ ] (P3, S) **`draft` propagates along a tangent chain with no UI/doc warning.**
      After an r4 corner fillet makes all four walls tangent-continuous, drafting
      the ONE picked +X face tapers all four walls plus the four fillet cylinders
      (1361.7627 mm³ removed vs 314.9581 for the named face). OCCT-correct
      (`BRepOffsetAPI_DraftAngle` propagates through tangent continuity) and
      usually desirable, but a picked-face UI never says so — doc + editor copy.
      Pinned by `test_observed_limit_draft_propagates_along_a_tangent_chain`.
      [src: GEOMETRY-QA 2026-07-25 composition matrix]

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

- [ ] (P3, XS) **SPEC-2 — `qa-sel4-verify.spec.ts`'s hidden-body leg sits on its
      own timeout ceiling** (`apps/web/e2e`). Found 2026-08-11 by qa-tester: the
      test declares `test.setTimeout(180_000)` and measured 2.5 m and 2.9 m in
      isolation and 3.0 m in a five-spec run, where it FAILED on the ceiling —
      i.e. ~17 % headroom on a gate whose cost grows with the canvas sweep. Not a
      product defect (it passes alone, twice), but a red CI shard waiting for a
      slower runner. FIX: raise the budget or thin the sweep; same class as the
      contention-robustness hardening already applied to the founder-flow specs.
      [src: qa-tester, SEL-7 verification 2026-08-11]

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

### QAH-1 CLOSED — found outside the range this groom pass first searched (2026-08-15 evening, backlog-groomer, corrected by the orchestrator)

- **QAH-1** — e2e CI's "renders while orbiting" failure
  (`qa-harness.spec.ts`, `Expected > 0, Received 0`). ROOT CAUSE: the
  render-clock COLLECTOR, not the product — `diagnostics.ts:193` read
  `rendersInProbeWindow: … ? null : 0, // MUTANT: always 0`, a mutation-test
  constant `0580f7d` committed as product code while reconciling a stopped
  agent's work without running its own e2e gate. FIXED `c3019b6`: measured
  live, the scene rendered 38-48 times and the camera moved ~18 units while
  the collector reported 0; post-fix the same window reads 9-of-9 frames
  backed by a render. Ablated both directions (constant 0 -> red at the
  orbiting assertion with CI's exact message; constant positive -> red at
  the settled-scene assertion) and CI itself shows the target assertion
  passing at `c3019b6`. A second, independent defect found while verifying
  (`waitForQuiet`'s 20s wall-clock budget failing deterministically under
  load, unrelated to the collector) fixed in the same commit.
  **NOT the same defect as `8d5be24`'s `cameraPose: no camera captured`
  race** (a different spec, a different mechanism — the probe reading before
  the scene's first render vs. a broken render counter) — kept apart
  correctly by this pass even while the range error below was live.
  **PROCESS NOTE, the reason this needed a second look:** `c3019b6` is an
  ANCESTOR of `a658db4` (`git merge-base --is-ancestor c3019b6 a658db4` ->
  yes), so it was invisible to `git log a658db4..HEAD` — the range this
  groom pass's dispatch brief specified. Re-deriving *inside* the given
  range found nothing and produced a confident, well-evidenced, WRONG
  conclusion ("no commit touches this assertion") — re-deriving is only as
  good as the window it searches, and a truncated window can make "found
  nothing" look identical to "there was nothing to find." The brief itself
  was also wrong in a smaller way (QAH-1 was never ticked, because the
  groomer held the board when it shipped and the fix's author chose not to
  contend for it). Caught by the orchestrator re-reading `git log` against
  the correct range, not by anything this pass did differently.

### Reconciled from Ready — the founder's four 2026-08-01 sketcher reports all now answered (2026-08-15 evening, backlog-groomer)

- **DIM-1** — dimension VALUE field silently wrote wrong geometry (`125` over
  `43` -> `435`, no error). FIXED `a810524` (uncontrolled input, ref-backed).
  Gate flipped from characterization to positive `810d9fb`, band widened to
  `[60,100,150,200,250,60]` ms after ablation showed the original band passed
  on a broken build ~1/3 of the time. NOT independently code-reviewed or
  QA'd (fix and gate were written by two different agents, the nearest thing
  to independence here).
- **SNAP-1** — founder "snap points not working." NOT a snap-detection bug:
  snap detection/placement measured correct in every buildable configuration
  (`dbd7140`, 6 new specs). CLOSED as a duplicate of SKETCH-2 — the founder
  could aim at the origin/axes and could not select them to constrain to.
- **SKETCH-2 (M2)** — origin and axes made selectable constraint targets via
  lazily-materialised pinned construction geometry (`5ceed6e`). Independent
  QA (`c82ff09`) verdict PASS on the founder's complaint, with four defects
  filed (QA-SK2-1..4 in `docs/UI-REVIEW.md`). Follow-up fix `8f00dec`/`09cec01`
  closed the BLOCKING finding (symmetric-about-a-datum-axis reported
  OVER-CONSTRAINED pointing at an undeletable, invisible pin — fixed by
  filtering pin indices out of the solver's reported conflict/redundant sets
  at one seam) plus QA-SK2-1 (the fixture wasn't actually rigid — fixed, all
  four corners now verified) and QA-SK2-2 (modifier-click ordering so a
  corner already at the origin can reach it). **Two QA findings remain open,
  filed separately: QA-SK2-3 (Finish-button click drop) and SNAP-2 (snap
  copies coordinate, infers no constraint — Ready, P0, the sharpest reading
  of "snap points don't work" left standing).** Two numbers corrected by
  review during this arc, both now fixed everywhere they appear: unit tests
  1622->1659 (37 new, not 15); the origin-ring pick margin is
  viewport-dependent (9.37 px at 1600x1000, 7.17 px — inside tolerance — at
  1280x800), not "misses by construction" universally.
- SKETCH-1, VP-1, VP-1a — all QA'd green (`6df1170`), still **none reviewed
  by `code-reviewer`** — flagged, not re-filed as separate tickets; the debt
  is the same class as K8 and belongs on the orchestrator's radar, not the
  board.
- **Mutation/debug-marker CI gate** (`56297d2`, `scripts/check-mutation-
  markers.py`) — the grep-level guard `docs/RETRO.md` §4b asked for after
  `0580f7d` shipped a stopped agent's `// MUTANT: always 0` as product code
  with nothing but e2e able to catch it. Wired into `just lint` + CI;
  23-case self-test, two negative controls on its own acquitting rules, a
  non-vacuity floor (MIN_FILES=300) so a broken walk can't report clean. No
  BACKLOG ticket tracked this ask before it shipped — process gap, noted so
  the next RETRO-sourced ask gets filed rather than done silently.

### Reconciled from Ready — DIM-1 QA / QA7-1 / GEOM-2 / FB-19 groom pass (2026-08-15, backlog-groomer)

- **QA7-1** — the SEL-7 Create-costs-nothing wait was vacuous and the two
  comparison arms sampled at different settle depths. SHIPPED `db144d7`,
  REVIEWED non-blocking (3 green, 1 amber). Amber follow-up filed as QA7-1b
  (scanner recognition gap + repo-wide promotion, Next). QA never ran on this
  slice itself (the verify agent died on a session limit) — no product-code
  risk (the fix is e2e-file-only), noted for completeness.
- **GEOM-2 (M17)** — tier 4 (`enclosing_face_match`) anchors a planar face's
  identity on its OUTER boundary, fixing the thickness-edit-orphans-holes case.
  SHIPPED `8b95dac`. Code-reviewed `57711c4` (corrected the design doc's own
  account of what moved: 3 goldens + a rename, not the "one" first claimed;
  the M17 top-face centroid measurement; and that only the band's UPPER bound
  is derived, the lower is a well-motivated assumption). That review also
  QUANTIFIED the honest limit `docs/design/topological-naming.md` §12a only
  described qualitatively — see GEOM-3 (Ready, P0), now the actual next step,
  plus GEOM-4/GEOM-5 (Later) for the smaller follow-ups it also found.
- **FB-19** — chrome density (label-beside-control `FieldRow` primitive).
  SHIPPED `f7c41d9`. Still not reviewed, not QA'd, screenshots not sent to the
  founder — tracked as FB-19b (Next) rather than closed here, per the K8
  convention (an `(UNREVIEWED)`-class item stays visible until both gates
  pass).
- **QA-VERIFY-1 CLOSED** — both specs it asked to verify have now run:
  `sketch-orbit.spec.ts` (VP-1) 7/7 pass, `sketch-reopen.spec.ts` (SKETCH-1)
  pass plus a new save/reload/re-open round trip, both executed as part of the
  DIM-1 QA pass (`6df1170`, 2026-08-15) rather than by a QA-VERIFY-1-labeled
  task — the acceptance criterion (run both, note the result) is met either
  way. SKETCH-1/VP-1/VP-1a below updated from UNQA'D to QA'd-green,
  code-review still outstanding.

### Reconciled from Ready — c449235 review groom pass (2026-08-14, backlog-groomer)

- **SKETCH-1 (M15)** — a saved sketch can be re-opened via `beginEdit`
  hydration; SHIPPED `30a9f3f`. QA'd green 2026-08-15 (`6df1170`: pass, plus a
  new save/reload/re-open/dimension-still-60 round trip). Still UNREVIEWED by
  `code-reviewer`.
- **VP-1** — orbit while sketching on MIDDLE button; SHIPPED `43c703c`. QA'd
  green 2026-08-15 (`6df1170`: `sketch-orbit.spec.ts` 7/7). Still UNREVIEWED
  by `code-reviewer`. Fragile mechanism, noted not filed as its own item: the
  sketch-mode `mouseButtons` binding relies on r3f REPLACING rather than
  merging the `mouseButtons` object prop (`Viewport.tsx:880-887`) — if a
  future three-fiber/drei upgrade ever merges instead, LEFT silently regains
  ROTATE and the sketcher's press-drag starts orbiting. Watch this on any
  r3f/drei version bump.
- **VP-1a** — Alt(Option)+left-drag orbit reaches trackpads; SHIPPED
  `32e5b87`. UNREVIEWED by `code-reviewer`; QA coverage rides VP-1's spec
  above (same binding path). Follow-ups filed: VP-1b (undiscoverable gesture,
  Next) and QAH-1 (possible CI orbit-probe regression, Ready).
- **c449235 (Dimension verb arms instead of dead-ending)** — SHIPPED,
  reviewed (`d6fc92b` corrected two integration errors from this pass:
  stale worktree SHA citations, and this item's parent left `[x]` while its
  own acceptance was unmet). Follow-ups filed: DIM-1 (P0, keystroke loss —
  the probable real founder experience, now confirmed by QA as silent
  WRONG-GEOMETRY writes — `6df1170`), DIM-3 (armed-state flow bugs), ESC-2
  (FB-13 landmine in a duplicate Escape cascade), ESC-3 (test gap).

### Reconciled from Ready — backlog hygiene sweep (2026-08-14, backlog-groomer)

104 items were sitting checked `[x]` (or, for CI-3, shipped but never ticked)
inside "Ready (top of queue)" going back to 2026-07-23 — the section had grown
to ~2,850 lines against the 5-10 item target. Full narrative evidence for all
of these lives in `docs/ROADMAP.md` and `git log`; one line each below.

- **FB-20 (camera stolen after extrude)** — fixed 2026-08-14 (`d091112`);
  UNREVIEWED (K8) — no independent code review or QA pass yet.
- **CI-3 (gateway 502 on dropped keep-alive)** — fixed 2026-08-14 (`a2bb859`);
  UNREVIEWED (K8) — no independent review or QA pass yet.
- SPEC-4 — sketch-visibility's ink census measured by coverage, not exact
  token. CLOSED-PENDING-QA, no independent QA pass yet.
- SEL-7 — hole placement withholds its overlay from a hidden placement body.
- SEL-4 — armed edge/shell/draft picks got the shared raycast hit-test.
- CI-1 — sketch-visibility gate given a CI run + separation floor.
- FB-1/1b — extrude/sketch-on-face stopped "flipping to xy" / not drawing.
- FB-2 — a sketch line selects reliably.
- FB-3 — face picking hit-test widened.
- FB-4 — a cut extrudes into material, not away from it.
- FB-5 — hovering a face offers "sketch on this face".
- FB-6 — sketch ink visible on the face it sits on.
- FB-7 — editor panels dock into a movable rail.
- FB-10 — drawings dimension edge-to-edge (shell wall thickness).
- FB-11 — the app states its build/version.
- FB-12 — a 5px click drift no longer silently discards the pick.
- FB-13 — Escape with nothing selected no longer ends the sketch.
- FB-14 — a plain click replaces the pick set instead of accumulating.
- FB-15 — draw tools support click-and-drag, not just click-then-click.
- FB-16 — dimensions typed inline while drawing.
- FB-17 — browser e2e suite gained gates for the founder's defect class.
- FB-22 — a sketch origin/frame marker, snappable, on the sheet.
- FB-23 — sketch-local undo/redo stack.
- CONC-1..4, CONC-6 — session affinity, admission control, geometry-service
  timeout honesty, rebuild-cache sizing, prefetch head-start — all shipped.
- LIC-1..5 (incl. duplicate LIC-4 id) — GPL/LGPL/GCC-runtime licence hygiene,
  bundled-binary scanning, `pnpm --port` footgun — all closed.
- PERF-1, PERF-1b, PERF-2..5b — rebuild cache, mid-tree edit cost, validity
  gate cost, STEP-import DoS bound, mesh compression, glTF fusion, per-face
  provenance — all shipped (`docs/PERF.md`).
- OPS-1 — backup, restore, restore test.
- Audit N4 tail — exported STEP/drawing filenames carry the document name.
- #58 — Settings surface, every row wired.
- #WS1, #WS2 — workspace search/sort/rename/duplicate/delete + folders.
- F3, F4 — feature-delete dependency warning; keyboard-shortcut help.
- Assembly panel mass rollup (stopped promising a mass with no material).
- QA-1/CM-6, QA-2, QA-3, QA-4, QA-4b — mirror validity, thickness-edit hole
  destruction, dimension-survives-revision, lost-dimension-on-print (both
  screen and export) — all fixed.
- #57, #57b — mass properties (kernel + wire + UI gating on material).
- UI-W1, UI-W2, UI-W3+W4, UI-W5 — timeline strip, per-instance visibility/
  isolate, pre-selection + pinned references, entity snapping.
- UI-REVIEW 2026-07-30 P1/P2/P3 — export-strip fold, timeline redundancy
  claims, three silent gates.
- CM-1..4 — mirror-erases-cut, pattern-of-cut no-op, cut-removes-nothing,
  composed-body STEP topology — all fixed; friendly `cut_removed_nothing`
  copy shipped.
- Mirror v2 — mirror a selected set of features (web authoring included).
- "Is broken" register state, `eval_state` column, F2 staleness, J3/J3b
  rollback-prefix verdict scoping, J2+N3+F2-frontend, sheet-number identity —
  all shipped 2026-07-30/31.
- Composition-matrix gate, jsdom component-test tier — structural test-gap
  closures from the production-readiness assessment.
- Assembly STEP export (AP214 product structure), E1a/E1b (section views wire
  + web authoring), assembly interference/collision detection (+ false-
  negative fix + unresolved-clash panel surface), assembly STEP import
  (product structure, `body_step` dedup, permanent 3-service integration
  test) — the "assembly is a one-way street" gap closed 2026-07-23/25.
- Dedicated Hole feature slices 1 + 2 (geometry + web, counterbore/
  countersink), feature suppress, mirror feature (kernel), gateway E2
  (assembly export/interference web wiring), revolve construction-centerline
  axis (kernel + web), datum editor midplane face-sides.
- 2026-07-24 hard-audit P0/P2 batches, FINDINGS #6/7/8/9/10/15/21 — command
  band, tooltips, live extrude-preview ghost, feature-localized selection,
  right-click context menus, drawings/HLR burn-down, assembly STEP PRODUCT
  naming, register template-feel fixes.

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

- 2026-08-15 — **Groom pass 4 (backlog-groomer):** DIM-1 moved to top of Ready
  (QA `6df1170` found it writes silent WRONG geometry, not just a slow field);
  archived QA7-1/GEOM-2/FB-19 shipped, QA-VERIFY-1 closed; filed GEOM-3/4/5
  (GEOM-2's quantified honest limit + durable fix) and TOUCH-1 (no touch
  Playwright project). Older entries: see `docs/CHANGELOG.md`.
- 2026-08-15 evening — **Groom pass 5 (backlog-groomer):** all four founder
  2026-08-01 sketcher reports now answered; archived DIM-1/SNAP-1/SKETCH-2 +
  the SKETCH-2 follow-up fix (`8f00dec`, closes the blocking symmetric-datum
  bug + QA-SK2-1/2). Filed SNAP-2 (P0 — snap infers no constraint, silent
  drift on redrive), SKETCH-3, TOUCH-2, QA-SK2-3, SPEC-6/SPEC-7. Credited the
  mutation-marker CI gate (`56297d2`) with a Done entry it had none of.
  Wrongly concluded QAH-1 still open — corrected below, same evening.
- 2026-08-15 evening — **Groom pass 5 correction (orchestrator-caught):**
  pass 5 searched only `a658db4..HEAD` (the brief's range) and found nothing
  touching QAH-1's assertion; the fix (`c3019b6`) is an ANCESTOR of
  `a658db4`, invisible to that window. **QAH-1 is CLOSED** — see Done
  archive for the evidence. Re-deriving from git log is only as good as the
  range it searches.
