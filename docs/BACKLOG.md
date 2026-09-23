# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), `docs/COMPETITIVE.md`,
and the roadmap. The autonomous build loop pulls from **Ready (top of
queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Frontend redesign — wave log (orchestrator, not the groomer's queue)

The redesign loop (`.claude/workflows/loft-frontend-redesign-loop.js`) works
from `docs/design/REDESIGN-ROADMAP.md`, not from the Ready queue. This section
is the landing record only, so the board is not silent about shipped work.

- [x] (P0, M) **FLOW-A1** — a size typed in the first frames after a draw is no
      longer discarded; the part no longer comes out silently wrong `2a90a92`
      [docs/design/AUDIT-FLOW-2026-09.md]
- [x] (P0, L) **FLOW-A2** — Back, the breadcrumb and reload can no longer eat an
      unsaved sketch; guard + per-part draft `501331b`
      [docs/design/AUDIT-FLOW-2026-09.md]
- [x] (P0, M) **W0REV modal-gate fix** — the blocking review finding (Enter on
      the exit prompt applied the armed draw dimension instead of saving/
      leaving; `Ctrl+Z` leaked into the sketch behind the modal too) plus two
      more (a save in flight blurred the dialog and dropped its own focus
      trap; sketch drafts outlived sign-out) — one capture-phase
      `lib/modalGate.ts`, not a patch per listener `da98622` [W0 code review,
      2026-09-12]
- [x] (P1, M) **FLOW-B2** — `K E R F C` bound for Sketch/Extrude/Revolve/
      Fillet/Chamfer, the five verbs a hand reaches for most, which had no
      keys while seven rarer ones did `d5e936a`
      [docs/design/REDESIGN-ROADMAP.md W2]
- [x] (P1, M) **FLOW-B1** — a solved sketch writes `EXTRUDE ⟨E⟩` on its own
      profile, closing the single largest measured flow gap (8 of the 15
      hunts the audit recorded) `78aaa67`
      [docs/design/REDESIGN-ROADMAP.md W2]
- [x] (P1, S) **FLOW-B3** — exactly one command-band tool wears the next verb
      after a build completes, gated by name rather than divination
      `fb63809` + `6097448` [docs/design/REDESIGN-ROADMAP.md W2]
- [x] (P1, M) **CRAFT-6** — the reference cube persists through plane-pick and
      sketch instead of unmounting with the view rail; facet clicks measured
      to steer the camera (41.85°/45.00° turns), the orthographic preference
      frozen for the duration of authoring `a340ff5`
      [docs/design/AUDIT-CRAFT-2026-09.md]
- [x] (P1, L) **CRAFT-1/2/3** — a filleted body now draws its edges (was 0 —
      the crease detector cannot see a tangent fillet; fixed off the
      tessellation's own face partition), a front/right/top orthographic view
      keeps its ground plane (was empty by construction, not a fade issue —
      a plane containing the view direction projects to a line under a
      parallel camera), and the origin triad is drawn at rest, dimmed
      `57d3bf8` [docs/design/AUDIT-CRAFT-2026-09.md]
- [ ] (P1, S) **W0REV-3** — sketch drafts are never swept: `DRAFT_MAX_AGE_MS` is
      checked only on read of that one key, so 50 parts leave 50 buffers on disk
      indefinitely. A full quota then degrades `auth/session.ts` silently, which
      reads as "logged out on reload" and will never be traced here. Needs the
      storage seam widened to allow a key scan [W0 code review, 2026-09-12]
- [ ] (P2, M) **W0REV-5** — the unsaved-sketch guard lives inline in
      `PartPage.tsx` (~5,690 lines) rather than the `useUnsavedSketchGuard` hook
      the audit specified, so the two order-dependent effects, `unsavedSketchRef`
      and the `leaveSaving` machine have ZERO unit coverage — protected by a
      comment that overclaims: reorder them and the first exit may go unguarded
      QUIETLY, not loudly [W0 code review, 2026-09-12]
- [ ] (P2, M) **W0REV-6** — third hand-rolled modal shell;
      `LeaveSketchPrompt` duplicates `ShortcutSheet` nearly line for line
      (backdrop, stopPropagation, tabIndex, focus save/restore, header band).
      Per "extract on the second real use" this is the trigger, and the
      extraction is where the modal key-gate and focus management belong ONCE
      [W0 code review, 2026-09-12]
- [ ] (P3, S) **W0REV-7** — "Dismiss" on the restored-draft note only hides the
      banner; the draft stays and the sketcher stays open on a buffer the user
      may not have wanted back. Ambiguous exit inside the feature whose whole
      thesis is unambiguous exits [W0 code review, 2026-09-12]
- [ ] (P2, S) **W0REV-9** — the buffered replay path has no test that can fail on
      it: the e2e gates the OUTCOME, which is identical whether the buffered or
      the mounted path ran, so on a fast enough machine the buffer code is never
      exercised and the suite still passes [W0 code review, 2026-09-12]
- [ ] (P3, S) **W0REV-10** — Tab as the very first key diverges between the two
      paths: mounted focuses cell 0, buffered replays to cell 1. Same keystroke,
      two answers, decided by a race [W0 code review, 2026-09-12]
- [ ] (P3, S) **W0REV-11** — two tabs on one part cross-restore: tab 1 writes the
      draft, tab 2 restores it and announces "Draft restored" for work that was
      never lost; both then mirror and both can save it [W0 code review]
- [ ] (P2, S) **DIMEDIT-KEYS-1** — the THIRD address of the dropped-keystroke
      family: `dimension-editor`'s cell is also inside a commit that trails the
      click opening it. Unmeasured — FLOW-A1 could not check it, `routes/` was
      held by a sibling [FLOW-A1 builder report, 2026-09-12]
- [x] (P2, M) **W2 code-review fixes** — `? then E` opened Extrude BEHIND the
      open key card and a focused button's Enter/Space was stolen by an
      `isTypingTarget` guard that does not cover buttons — the same "each half
      correct, wrong together" shape W0REV found, on `ShortcutSheet`
      (`6602ccd`, `activationKeyOwner` + a leak alarm; 22 pre-seam listeners
      named, not migrated — MODALGATE-MIGRATION-1 stays open below). Plus five
      smaller findings, all fixed: a chip's one-shot spent on an offer never
      drawn (`356ac66`); the chip's seed opening the wrong sketch on a raced
      refetch/undo (`46c8e6f`); a coverage floor that was vacuous — deleting
      its own row still passed the file it lived in 7/7, the real guard is
      elsewhere (`f317ac5`); `REPEAT_ROWS` keyed by bare `string` instead of
      the generated feature-type union (`6de8fdf`); the next-verb accent
      wearing "round it now" for an extrude built last week (`b7b7f12`);
      comments corrected to match (`bbb5ed3`). [docs/design/
      REDESIGN-ROADMAP.md W2 review, 2026-09-13]
- [x] (P1, M) **XWAVE-1 — a hidden body kept its brass feature outline; the
      branch tip was e2e-RED since `57d3bf8`, not a census artifact.**
      CRAFT-1's edge-overlay swap (crease detector -> real face partition)
      gave a latent hole in `ModelMesh`'s two edge-material paths enough ink
      to draw: hiding the plate left 667px of face-boundary outline floating
      in the void. DOM assertions all passed — only the GL ink was wrong.
      Fixed by deriving both paths from one `litFeatureFaces` precedence
      (`0c3e363`). [src: cross-wave QA, `docs/QA-REVIEW.md` 2026-09-13]
- [x] (P2, S) **XWAVE-2 — the solve-proposal chip rendered OVER the reference
      cube and took its clicks.** The chip is the later `z-hud` sibling — 29%
      of the cube's seat taken including its exact centre, and a real click
      there opened Extrude instead of reorienting. `placeProposal` now tries
      four quadrants against `measureChrome`'s live `data-viewport-chrome`
      rects; a click landing on chrome no longer burns the one-shot offer
      (`76a214c`). [src: cross-wave QA, 2026-09-13]
- [x] (P2, S) **XWAVE-3 — CRAFT-6 made the bottom-right corner dead to face
      picking.** The cube's `z-hud` layer sits above every pick mark by
      construction; 5 of 6 `plane-pick-face-N` marks and the surface pick
      itself went dead under it. The cube now yields its pointer while a pick
      is ARMED and takes it back the instant the pick ends; orbit/pan/zoom
      untouched (`d0a3190`). It deliberately does NOT extend to ordinary
      drawing — see **CUBE-SKETCH-OCCLUDE-1** below, the product decision
      this leaves open. [src: cross-wave QA, 2026-09-13]
- [x] (P3, S) **XWAVE-4 — one Escape backed out two steps, in every
      configuration with two things to back out of.** Three uncoordinated
      `window` listeners, order decided by mount time. `lib/modalGate.ts` now
      declares one cascade (`drag > offer > mark`), run exactly one rung
      (`dbb09fb`). [src: cross-wave QA, 2026-09-13]
- [ ] (P2, M) **CUBE-SKETCH-OCCLUDE-1 — during ordinary sketching, the
      reference cube's 108x108 seat in the bottom-right silently eats
      gestures aimed at the scene underneath it.** kind: question (product
      decision, not a defect). MEASURED: at a zoomed-in leg on a 1600x1000
      frame, a point that is genuinely empty sketch space maps to (1519, 903)
      — inside the cube's seat — and `elementFromPoint` there returns the
      cube's canvas, not the scene's; a click lands on the cube and steers
      the view. THE STATE OF PLAY, so this is honest about what is already
      handled: `d0a3190` made the cube yield its pointer while a FACE PICK is
      armed (the plane-pick corner went from 5-of-6 marks unreachable to
      0-of-6), counted through `armedPicks.ts`/`PickMark`. Sketch datum
      handles are drei `Html`, not `PickMark`, so during ordinary DRAWING
      `armedPicks` counts zero and the cube does not yield — `d0a3190`
      explicitly decided drawing never yields it, on the grounds that the
      sketcher's snap marks are not pick marks. So this is a genuine trade
      CRAFT-6 made ON PURPOSE (orientation matters MORE while drawing on a
      plane in space, not less), not an oversight, and the cost is that one
      corner of the sketch plane is not directly drawable. OPTIONS for a
      builder to weigh, not adjudicated here: (a) extend the pick-armed yield
      to drawing/snap gestures too; (b) shrink or inset the cube while
      sketching; (c) let a drag that STARTS on the scene (pointerdown outside
      the cube's rect) pass through even if it crosses the seat; (d) accept
      it and document the dead corner as a known limitation. ACCEPTANCE: a
      decision recorded in `docs/design/REDESIGN-ROADMAP.md` or
      `docs/VISION.md` with its reasoning, and either the cube gains a yield
      mechanism for drawing or the trade is documented as deliberate with a
      regression test pinning today's behaviour. Cross-reference: CRAFT-6
      (`a340ff5`) made the original trade; VIEWFRONT-ORTHO-DECISION-1 is the
      same shape — a deliberate behaviour nobody actually decided
      deliberately. [src: cross-wave QA + `d0a3190` follow-up, 2026-09-13,
      `docs/QA-REVIEW.md`] TERRITORY: `apps/web/src/viewport/armedPicks.ts`,
      `apps/web/src/components/AuthoringViewCube.tsx`,
      `apps/web/src/viewport/ViewCube.tsx`. agentType: frontend-builder
      (decision may need founder/vision-steward input first, same as
      VIEWFRONT-ORTHO-DECISION-1).
- [x] (P1, L) **CRAFT-8** — `<ParametricGauge>` extracted out of
      `ExtrudeDragHandle` (601 -> 88 lines), a four-way split forced because
      `packages/design` has no r3f; the shared foundation CRAFT-7/9/10/11
      build on `4b0465d`. Review found three, all fixed: a gauge-override
      handle that churned a global listener once per drag frame (`b20e8ce`),
      the ask-queue's rules made deterministic — its old positive control had
      fired 2 of 12 runs (`fd1156a`), and `extrudeTrack`'s seam given the unit
      coverage the 36-case e2e suite could not provide (`730b2ae`)
      [docs/design/REDESIGN-ROADMAP.md W3]
- [x] (P0, L) **CRAFT-7 — CLOSED.** The extrude gauge is grabbable: reach 2 of
      16 -> 16 of 16 sample points along its own projected axis; a real mouse
      drag from the shaft midpoint now moves the value where it previously
      left it at 40. Also: the zoom-aware snap (sampled once on arm and frozen
      thereafter — 40 wheel notches moved the shaft 3.86 -> 28.48 px/mm with
      the snap never updating), the spine drawn as a polyline rather than a
      chord, the readout became an input with digit capture, nested Escape, a
      leader on the tag `6864f82` + `e25f125`. **Its blocking review finding is
      now FIXED (`c9e037c`):** the px/mm scale divided a projected
      seat->arrow-TIP length by a WORLD seat->arrow-BASE length, so the
      original commit's own "14 px floor" was really ~11.9 px at depth 40 and
      ~9.7 px at depth 10 — every figure the commit reported was measured
      against the biased quantity. Fixed via `projectedSpineLength` in
      `gaugePose.ts`; the split snap-ladder floor (`majors >= 14px`,
      `pitch >= 7px`) that was gating on it needed no further change. Measured
      drawn pitch off the spine mesh's own `matrixWorld`, before/after, at two
      widths — 1600x1000: 2mm 12.07 -> 7.23px; 1280x800: 2mm 11.35 -> 7.15px
      (the 12.07 independently reproduces the reviewer's 12.08). `angularTrack`
      inherited and shares the same fix (relevant to CRAFT-10). `e56c9bc`
      separately re-derived the grip's e2e size tolerance as Blink's 1/64 px
      LayoutUnit quantum — the float32-ULP reading it replaced was only
      correct for x in [512,1024) and silently doubled past 1024.
      **CRAFT-9a/9b/10/11 are now unblocked and IN FLIGHT — see entries below.**
      Bisect note, kept for the record: `6864f82` (part of this item) has NO
      CI run of its own — pushed in the same event as `e25f125`, which fired
      one run keyed to the head commit — locally verified standalone
      (typecheck clean, 233 design + 2461 web tests) and tree-verified by
      `e25f125`'s green run, NOT CI-verified; keep that distinction if this
      commit is ever a bisect endpoint.
      [docs/design/REDESIGN-ROADMAP.md W3, §8 DIRECTION-W3-PROPOSALS.md]
- [x] (P2, S) **e2e verdict reporter** — a red shard named the failing test
      and withheld the reason: `results[].error.message` was being dropped
      from the summary block `6043601`.
- [ ] (P3, S) **CRAFT-INTERMITTENT-1 — one of its two cases is now CLOSED,
      and the closure PARTIALLY REFUTES this ticket's own classification.**
      (a) `rect-rigidity.spec.ts:281` — still open, unchanged; red on 2 of 5
      recent CI runs, 31 local executions across seven stress axes gave zero
      failures, persisted constraint set byte-identical every time. (b) was
      `qa-cross-wave-0913.spec.ts:572` "the cube is a control again once the
      pick is over" (also seen at `:253`), filed as ONE intermittent because
      both lines shared a symptom (a cube-facet click not moving the camera)
      and both wandered their failure point. **They were not one cause.**
      `36360ae` (groom pass 27) root-caused the `:253` case (now "a click on
      the cube steers the camera and keeps the offer"): a fixed 800ms sleep
      read `data-camera-pos` before the click's camera ease had landed under
      load — a real assertion-timing defect, not an unreproduced race,
      fixed by polling the settle stamp the ease itself writes
      (`onSettle` → `data-view === "direction"`). 7/7 red under load before,
      7/7 green after; two new assertions each seen to redden (dropping the
      click, or a precondition violated). This satisfies the ticket's own
      ACCEPTANCE for that half ("root-cause at least one to a specific race
      rather than filing it as CI is noisy") and means the "DELIBERATELY NOT
      touched" argument below did not hold for this half — the fix did not
      consume an evidence trail, it found the defect the trail was made of.
      **The `:592` sibling (renumbered from `:572`; "the cube is a control
      again once the pick is over" itself) still uses the SAME unfixed
      pattern** (`page.waitForTimeout(800)` then compares `data-camera-pos`)
      — filed separately as QA-CUBE-YIELD-SETTLE-1 (groom pass 27) rather
      than folded back in here, since it is now a known fix shape, not an
      open investigation. **Still applies to `rect-rigidity.spec.ts:281`:**
      shipping a synchronization fix without a reproduction would destroy
      the only evidence a future red run could hand a root-causer; that
      reasoning is now proven right in one direction (don't guess) and wrong
      in another (a suite that "produced zero reproductions" can still hide
      a provable, load-sensitive defect — the `:253` case reproduced 7/8
      under load and 0/8 quiet, which the ticket's local stress runs may not
      have matched). ACCEPTANCE (rect-rigidity only, going forward):
      root-cause it under CPU load, matching the discriminator that worked
      here, before concluding it is unreproducible. `6043601`'s verdict-block
      fix means the next occurrence will name its own cause — use that
      first. [src: CRAFT-7 wave report, 2026-09-14; reconfirmed groom pass
      23; `:253` half closed and `:592` half split out, groom pass 27]
      TERRITORY: `apps/web/e2e/rect-rigidity.spec.ts`. agentType: qa-tester /
      frontend-builder.
- [ ] (P2, M) **ESLINT-HOOKS-1** — `react-hooks` is not in `eslint.config.js`
      at all, repo-wide: no `exhaustive-deps`, no `rules-of-hooks`. That gap
      is why CRAFT-8's handle-churn defect (`b20e8ce`, a global listener
      re-armed once per drag frame) was invisible until a human review found
      it. Turning the rule on is its own change with its own blast radius —
      at least three deliberate latest-ref patterns in the viewport will need
      documented exemptions rather than fixes. ACCEPTANCE: `react-hooks`
      added to `eslint.config.js`; every violation either fixed or exempted
      with a one-line reason at the call site; `just lint` stays green.
      Worth doing now — Wave 3 is adding a lot of hook-heavy viewport code
      and each new gauge (CRAFT-9/10/11) is a fresh chance to repeat CRAFT-8's
      bug. [src: CRAFT-7 wave report, 2026-09-14] TERRITORY:
      `apps/web/eslint.config.js` + violations repo-wide. agentType:
      frontend-builder.
- [ ] (P2, S) **EXTRUDE-RAIL-ESCAPE-1** — Escape while the extrude rail's
      numeric field holds unsaved typed text closes the WHOLE command and
      discards it; pre-existing, not CRAFT-7's. FB-13-shaped inconsistency
      (CLAUDE.md: "a key that sometimes saves and sometimes discards"): the
      gauge's own cell (CRAFT-7) now nests Escape and behaves BETTER than the
      rail field showing the identical number, so the same value has two
      different Escape behaviours depending which control holds it.
      ACCEPTANCE: the rail field's Escape matches the gauge cell's — cancels
      the unsaved edit and reverts the field, not the whole command — with a
      regression test covering both controls. [src: CRAFT-7 wave report,
      2026-09-14] TERRITORY: extrude rail field component (wherever
      `ExtrudeDragHandle`'s sibling numeric-entry lives). agentType:
      frontend-builder.
- [x] (P1, M) **CRAFT-9a — CLOSED (`1f32a67`).** Fillet radius + chamfer
      distance gauges. Band preview on every picked edge — the fillet closes
      with the round's arc, the chamfer with the bevel chord. Reach 16/16
      both verbs. Convexity is read from face CENTROIDS, not normals — a
      box's convex edge and a step's concave one present identical outward
      normals. Refuses rather than guesses on a closed edge with one planar
      face. [src: DIRECTION-W3-PROPOSALS.md §8.3/§9] agentType:
      frontend-builder.
- [x] (P1, M) **CRAFT-9b — CLOSED (`11a0906`).** Shell thickness + datum
      offset gauges. Shell draws the rim of the cavity the wall leaves —
      line-work deliberately: a ghosted solid would paint material exactly
      where the feature removes it. Both previews publish a QA stamp derived
      from the buffer handed to the renderer, never the value that produced
      it — needed TWO stamp functions, because a translating square has
      constant perimeter. **Open follow-up: `craft9b-gauges` contract-β is
      intermittent** — the rod springs back a step on release, 2/1/0 across
      runs on the base tree; see CRAFT-13 below. [src:
      DIRECTION-W3-PROPOSALS.md §8.3/§9] agentType: frontend-builder.
- [x] (P1, M) **CRAFT-10 — CLOSED (`7ecc480`).** Revolve sweep + draft angle
      on the 15°/5° ladder, **and it drew the revolve axis**, which did not
      exist in the viewport at all before this (a dropdown read "Y axis ·
      through the origin" with nothing on screen). **Its own follow-up,
      `894c6f3`: the hit sleeve now follows the drawn ARC rather than its
      chord** — reach was 0/16 with the chord sleeve, worse than the 2/16
      CRAFT-7 was raised to fix; found and fixed by this agent, which
      reverted its own out-of-territory file and escalated instead of
      leaving it. [src: DIRECTION-W3-PROPOSALS.md §9 CRAFT-10] agentType:
      frontend-builder.
- [x] (P1, M) **CRAFT-11 — CLOSED (`c0b5e5f`).** Pattern count + spacing
      gauges, two mounts on one feature. Ghost copies are simultaneously the
      preview and the count gauge's own stops; spacing keeps the tag, count
      carries `tag: "none"` because the ghosts ARE its reading — only one
      instrument may own the digits. **Follow-up `0c707b9`: the count
      gauge's seat left the frame** — its screen-space offset floor was
      written in world mm, so both `max()` floors selected their constant
      below 17 mm radius and stopped shrinking with the part while the
      camera-fitted frame kept shrinking. [src: DIRECTION-W3-PROPOSALS.md §9
      CRAFT-11] agentType: frontend-builder.
- [x] (P0, S) **Save-during-autosave race — CLOSED (`d227843`).** A ~280 ms
      window in which the one control that ends a sketch (Save) did nothing,
      silently, while an autosave was in flight; the queue already existed
      one layer down, the disable is what made it unreachable. [src: Wave 3
      cross-cutting finding, 2026-09-14] agentType: frontend-builder.
- [x] (P1, S) **CRAFT-12 — CLOSED (`7a15bea`).** A preview that would render
      outside the frame now triggers a bounded re-fit (outward-only,
      re-frame-never-re-orient, never mid-drag, once per command), measured
      11 mm-part pattern ghosts 5.9% -> 100% visible. Hardening the
      gauge/camera e2e against a real bug the re-fit's own scope surfaced:
      `readProposal` unions the whole `command-layer` group including
      RESTING sketch ink, so a release can re-fit the camera when nothing
      is actually out of frame — filed AND CLOSED same day as
      **CRAFT-12-READPROPOSAL-1** (`5274bea`) below.
      [src: Wave 3 close-out finding 1, 2026-09-14; closed groom pass 26]
- [x] (P1, M) **CRAFT-13 — CLOSED (`b4e7821`).** Root cause was NOT the panel
      field sync — it was a P0: `894c6f3`'s per-segment hit sleeve made band
      count a function of the value being dragged (a 120° sweep carries 32
      bands, 90° carries 24, keyed by index), so a shrinking arc sweep
      UNMOUNTED the band holding pointer capture mid-drag; Chromium emits no
      `lostpointercapture` for a removed capture host, so the drag froze
      permanently (measured live: value stuck at 90 after a grab near the
      seat, `data-grabbed` still "true" after mouse-up, bare-mouse movement
      then carrying the value 90→165 with no button held). Fixed by moving
      every pointer handler to the sleeve WRAPPER (lifetime = the gauge's,
      not the tessellation's) plus `if (event.buttons===0) endDrag()` at the
      top of `onPointerMove`, each verified by an independent negative
      control. The `craft9b-gauges` contract-β "intermittent" (rod springs
      back a step on release) is the SAME shape, confirmed rather than
      assumed: an unrelated `pointerleave` handler was incidentally flushing
      a stale `live` value via React commit, and the fix that correctly
      stops firing it exposed the settle that had always been required —
      both β cases now name it explicitly. Scope measured, not assumed: only
      revolve/draft (angular tracks) are affected; the other seven mounts
      build on `linearTrack`'s fixed two-point spine, one band always,
      re-run green. [src: Wave 3 close-out finding 2+3, 2026-09-14; closed
      groom pass 25]
      **FOLLOW-UP CLOSED groom pass 27:** the panel-field-sync lag this
      ticket ruled out as ITS cause was real on its own — seven of nine
      gauge-fed editors wrote their form from an EFFECT, one commit after
      the drag override, so a release could leave the drawn rod and the
      field one step apart for 2-4 frames. `3b7f9ad` fixed ExtrudeEditor
      (write during render, guarded by the override identity already
      applied); `357b91e` generalised it into `useGaugeFedForm`, adopted by
      all seven remaining editors. `gauge-release-sync.spec.ts` 12/12 after
      (was 3 failed/12), 0 disagreeing frames across a 10-drag timeline.
- [ ] (P2, M) **CRAFT-14 — every `disabled={someTransientFlag}` is a latent
      dead end.** kind: defect (systemic, audit first). `ToolButton` gives a
      consumer no way to distinguish "busy" from "gated" — both collapse to
      `aria-disabled` plus a swallowed handler. ACCEPTANCE: audit by the
      QUESTION (is this a refusal or a delay?), never by grepping the
      idiom — the last three defect-class audits that matched a shape missed
      every instance wearing a different one. Do NOT change the primitive
      first: the swallow is correct for genuine refusals; only add a
      distinguishable state for transient ones, once the audit names which
      call sites need it. [src: Wave 3 close-out finding 4, 2026-09-14]
      TERRITORY: `packages/design/src/primitives/ToolButton.tsx` + call
      sites repo-wide. agentType: frontend-builder.
- [ ] (P2, S) **CRAFT-15 — 3 of 12 points along a picked edge were already
      unreachable before any gauge mounted.** kind: defect, pre-existing
      (measured against a no-gauge control, not a W3 regression).
      PickMark/edge-overlay territory. ACCEPTANCE: reproduce on a control
      edge with no gauge attached, root-cause the 3 unreachable offsets
      (occlusion, hit-box shape, or z-order), and fix or document why they
      are structurally unreachable. [src: Wave 3 close-out finding 5,
      2026-09-14] TERRITORY: `apps/web/src/viewport/PickMark.tsx`, edge
      overlay. agentType: frontend-builder.
- [ ] (P2, S) **CRAFT-16 — should the shell gauge seat at the RIM rather
      than the face centroid?** kind: question (product decision). On a
      face the shell leaves open there is no wall along the centroid's
      normal — the wall is at the rim, in-plane, exactly where the preview
      already draws it. A rim seat would make the arrow and the outline one
      drawing. ACCEPTANCE: a decision recorded here or in
      `docs/design/REDESIGN-ROADMAP.md`, and if rim-seating wins, a builder
      moves CRAFT-9b's gauge anchor accordingly with before/after
      screenshots (CLAUDE.md design mandate rule 4). [src: Wave 3 close-out
      finding 6, 2026-09-14] TERRITORY: `apps/web/src/viewport/**` (shell
      gauge anchor). agentType: frontend-builder (decision may need
      founder/vision-steward input first).
- [ ] (P2, S) **CRAFT-17 — two competing e2e helper extractions must
      converge, and their `reach()` now mean DIFFERENT things — sharper than
      tidiness.** kind: DRY (CLAUDE.md non-negotiable) + latent test defect.
      `gaugeReach.ts` (CRAFT-9a) and `gaugeProbe.ts` (CRAFT-9b, since
      extended by CRAFT-10/11) both export `Point`/`projectedSpine`/
      `gripCentre`/`reach` and the same sample count + reach floor
      (`SAMPLES`/`REACH_SAMPLES`=16, `REACH_FLOOR`=12). **Confirmed by code
      review (`451245c`): `894c6f3` gave the two `reach()` implementations
      different SEMANTICS** — `gaugeProbe.reachAlongTrack` samples along the
      drawn polyline (where the bands actually are); `gaugeReach.reach`
      samples the chord. Harmless today only by accident of who imports
      which (`gaugeReach`→`extrude-grip-reach.spec.ts`/
      `fillet-chamfer-gauge.spec.ts`, both straight tracks where chord and
      polyline coincide; `gaugeProbe`→`craft9b-gauges`/`pattern-gauges`/
      `revolve-gauge`). The first arc-gauge spec that imports the wrong
      module gets a false red reading "the sleeve is broken" instead of "I
      imported the other helper". `gaugeProbe.ts` is the survivor — it is
      already the one CRAFT-10/11 built on. ACCEPTANCE: `gaugeReach.ts`'s
      callers move onto `gaugeProbe.ts`, `gaugeReach.ts` deleted, no
      behavior change (same reach numbers before/after on the specs that
      used it); if BOTH measurements (chord and polyline) are genuinely
      wanted, name them for what they are rather than overloading one
      `reach()`. [src: Wave 3 close-out finding 7, 2026-09-14; sharpened by
      code review P2-7, `docs/CODE-REVIEW.md`, `451245c`] TERRITORY:
      `apps/web/e2e/**` (gauge spec helpers). agentType: frontend-builder /
      qa-tester.
- [ ] (P2, S) **GAUGE-PROPORTION-1 — the rod-vs-graduation proportion
      problem generalizes past the 2 mm case CRAFT-7 fixed.** kind: defect
      (visual craft, tolerance). MEASURED: at pitch <= 0.5 mm, or on a very
      large seat (a 500 mm profile draws a 2.42 mm rod against a 1 mm
      `majorStep`), the rod is fatter than the graduation spacing and no arm
      rule fixes it — the mark is inside the thing it graduates, the same
      shape CLAUDE.md's screenshot-gate incident documents (a ladder can be
      correctly sized by its own rule and still invisible). CRAFT-7's
      per-class spacing bound (`majors >= 14px`, `pitch >= 7px`) closed the
      one case it was measured against (2 mm ladder, 0.97 mm rod) and does not
      generalize to either extreme above. ACCEPTANCE: a rule relating rod
      diameter to graduation pitch (not just screen-space spacing) that holds
      at both measured extremes, with a before/after screenshot pair per
      CLAUDE.md's design mandate rule 4 (a screenshot is the check that catches
      "present, correctly sized, invisible"). Relevant to CRAFT-9a/9b/10/11 —
      any of the four dispatched gauges can hit either extreme on a real part.
      [src: CRAFT-7 wave follow-up, groom pass 23, 2026-09-14] TERRITORY:
      `packages/design/src/gauge.ts`, `apps/web/src/viewport/
      ParametricGauge.tsx`. agentType: frontend-builder.
- [ ] (P2, S) **FORMATANGLE-MIGRATE-1 — migrate the three hand-written angle
      formatters onto `formatAngle`.** kind: DRY (CLAUDE.md non-negotiable).
      CRAFT-8 added `formatAngle` to `packages/design/src/units.ts` beside
      `formatLength`, deliberately WITHOUT migrating the existing call sites
      — converging `apps/web/src/measure/geometry.ts`,
      `apps/web/src/features/revolve.ts` and `apps/web/src/features/hole.ts`
      crosses three territories, so CRAFT-8 filed it rather than doing it.
      ACCEPTANCE: all three call sites format through `formatAngle` with the
      same `unitSuffix` option `formatLength` already has; no behavior change
      (same rendered text for the same value) — a pure DRY convergence, proven
      by a snapshot/unit test per site showing identical output before/after.
      [src: DIRECTION-W3-PROPOSALS.md §11.5, CRAFT-8 follow-up] TERRITORY:
      `apps/web/src/measure/geometry.ts`, `apps/web/src/features/revolve.ts`,
      `apps/web/src/features/hole.ts`. agentType: frontend-builder.
- [ ] (P2, S) **IMPERIAL-LADDER-1 — should the imperial snap ladder be a
      binary series?** kind: question (needs a measurement, not yet a
      decision). The ladder-as-snap-stops decision made the METRIC ladder a
      decade series (5 -> 2 -> 1 -> 0.5), but `SNAP_MM.in = 25.4/32` is a
      named, human step (a 32nd of an inch) and a decade ladder over it would
      replace that with a value nobody says out loud. The W3 direction's
      stated instinct is a **binary** series (1/32, 1/16, 1/8, 1/4, 1/2, 1 in)
      under the same screen floor — explicitly NOT decided, because no inch
      document was measured this pass. ACCEPTANCE: measure the ladder against
      a real inch-dimensioned part (drawn distances that land on 32nds), state
      which series a working engineer's eye actually wants, and implement
      that choice with the reasoning recorded in `docs/design/
      REDESIGN-ROADMAP.md` or this ticket — do not ship a silent default.
      [src: DIRECTION-W3-PROPOSALS.md §11.7] TERRITORY: `packages/design/src/
      gauge.ts` (ladder selection), `apps/web/src/routes/units.ts`.
      agentType: frontend-builder.
- [ ] (P1, S) **GAUGE-TOUCH-1 — a touch pass on all nine shipped gauge
      mounts, W3-exit QA gate.** kind: QA (not yet examined, flagged rather
      than guessed). The 24 px grip meets WCAG 2.2 SC 2.5.8 and CRAFT-7's
      hit sleeve is >= 12 px, but every reach measurement behind the wave —
      all nine mounts across all seven verbs — was mouse-driven, at
      1280x800 and 1600x1000 only; nobody has put a finger on any of these
      instruments. ACCEPTANCE: a real touch-emulated pass (Playwright touch
      input or an actual touch-capable device) on the extrude gauge and at
      least one of fillet/chamfer, shell/datum, revolve/draft, pattern,
      asserting the drag actually moves the value under touch pointer
      events, not just that the box is large enough. **Wave 3 is closed on
      the board this pass (groom pass 24, per orchestrator direction) with
      this gate still open** — noted as a tension, not resolved silently:
      the wave's build work is done and none of the nine open follow-up
      findings (CRAFT-12..17) block dispatching Phase 5 work in parallel,
      but this QA gate is real and still owed. Dispatch qa-tester on this
      alongside Phase 5 work, not instead of it. [src:
      DIRECTION-W3-PROPOSALS.md §11.4; reconfirmed groom pass 24,
      2026-09-15] TERRITORY: `apps/web/e2e/**` (gauge specs), touch harness
      (see PLAYWRIGHT-TOUCH-1 for the existing harness-gap item this may
      share infrastructure with). agentType: qa-tester.

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication. **Pass 8-19 detail moved to `docs/CHANGELOG.md` / Done archive.**

- **Groom pass 26 (2026-09-23, backlog-groomer) — 29-commit debt reconciled
  (largest batch yet); `e2e` is RED on the tip and is now the stated gate
  ahead of new feature dispatch.** `543aad9`'s `e2e` run failed 9 cases
  across shards 2 and 4 (`ci`/`deploy-path` green); an agent is already on
  the root cause. **CRAFT-12, VEC3-DEDUP-1 and CSP-1 CLOSED** (`7a15bea`,
  `4549da8`, `ed8c3d7`); **adjacency tier 3** (`bf05482`) closed the audit's
  `SUBSHAPE_UNRESOLVED` collapse for straight edges under a dimension edit,
  with curved neighbours (bore rims, fillet boundaries) recorded as an
  explicit residual. **VISION.md re-scored twice** (`ecb9df8`, `0fbfe81`):
  no capability row above parity, Performance ➖→❌. Filed 5 new items from
  the 2026-09-16 product audit and this pass's own e2e hardening, one of
  which closed the same day it was filed: **CRAFT-12-READPROPOSAL-1**
  (filed AND closed via `5274bea` — a released gauge lurched the camera on
  resting sketch ink; `readProposal` now skips tagged annotation roots),
  **PICK-PROXY-COLLIDE-1** (F-4: 48 of 110 Measure proxies unreachable at
  their own centre, plus systematic Fillet/Hole/Shell collisions),
  **MEASURE-LABEL-PITCH-1** (F-7: a 25 mm hole pitch reads `DISTANCE 17 mm`
  with no centre-to-centre option or label), **EDGE-RESOLVE-WARN-1** (no
  warning channel exists for a best-effort/silently-mis-resolved edge
  reference, sharper now that tier 3 is live), **INSTANCEOF-THREE-1** (15
  `instanceof` sites against three.js classes, correct in the shipped app,
  latent-broken for any future Viewport unit test). Updated the existing
  CI-numbers ticket with an orchestrator-read figure: the geometry job ran
  **21m57s** on a real CI run against the 30-min ceiling, confirming rather
  than superseding the local 21m20s estimate. **Board queue length: 201 →
  201 open items** (`grep -c '\[ \]'`) — closed 4 (CRAFT-12, VEC3-DEDUP-1,
  CSP-1, CRAFT-12-READPROPOSAL-1), filed 4 that remain open, net flat, which
  understates the pass: this is the largest reconciliation batch yet by
  commit count. Pruned groom passes 22-23's full Scorecard-gaps narrative
  into `docs/CHANGELOG.md`. ROADMAP "Current focus" reconciled to match.

- **Groom pass 25 (2026-09-15, backlog-groomer) — Phase 5's flagship SHIPPED;
  the gauntlet found and fixed a wrong-volume P0-adjacent defect; CRAFT-13
  closed.** 25 commits landed since pass 24's `87f4de4`, ALL carrying
  `Doc-tick: groomer` — the largest debt batch yet (prior largest was 12),
  reconciled in full this pass. Highlights: **SCRIPT-1 CLOSED** — the public
  Python scripting API (`import loft`) shipped, proven two-path-identical to
  a browser-driven build (12/12 facts, byte-equal STEP/STL hashes), then
  split into `packages/loft-wire` (a script's venv: 33 deps → 15). **F1/F2
  CLOSED** (geometry-qa's gauntlet, `0e3cc35`+`f7cd483`) — real-part volume
  was wrong by 1.49e-3 (1.58 L on a 1.07 m³ robot; no golden could ever fail
  for this — the bias is exact on planes/quadrics) and `mesh_glb_id` was
  non-deterministic across cache state; both fixed with a new golden and a
  structural gate. **CRAFT-13 CLOSED** (`b4e7821`) — root cause was a P0
  (an arc gauge's pointer-capture host could unmount mid-drag) plus an
  unstated settle masquerading as an intermittent; both fixed with a
  negative-control-verified two-part change. **Air-gap claim FIXED**
  (`725bc4b`) and **self-host path now reaches the app**
  (`977f492`+`093dfc1`, a `web` service existed nowhere before), each
  shipped alongside a CI guard that had manufactured its own failure
  (root-owned nginx pidfile; a job-level `${{ runner.temp }}` rejecting the
  whole workflow at zero jobs) — both now closed with dedicated gates.
  **Scorecard freshness gate shipped** (`b1bb1b6`) — the mechanical check
  VISION.md itself proposed after the 19-day-stale Assemblies incident;
  advisory only, and a code review found it has no PENDING deadline (filed
  SCOREFRESH-PENDING-1). **DIRECTION-ASSEMBLIES.md filed** (`21a039f`,
  vision-steward) — four items (PERF-ASM-1/PICK-ASM-1/BOM-ASM-1/FLOW-ASM-1)
  now on the board, BOM-ASM-1 replacing the old flat "RECURSIVE BOM" entry.
  A same-day code review (`451245c`, `docs/CODE-REVIEW.md`) found two P0s
  (both fixed same batch: the `delete_feature` 422 and the CRAFT-13 arc-drag
  P0) plus five P1s/P2s now filed: CONTRACT-PARITY-TEST-1, VEC3-DEDUP-1
  (four divergent Vec3 helper copies, already diverged in behaviour —
  a real NaN-propagation risk), SCOREFRESH-PENDING-1 (above), plus two P2
  process notes folded into existing items (CRAFT-17, gen-check's verdict
  line). **Scorecard gaps flagged for the vision-steward (not mine to score):**
  Extensibility (was ❌, PENDING on SCRIPT-1) now has a two-path-proof
  landed — re-score due; Free & unlimited / Your data-your-files (both
  PENDING on the air-gap/self-host audit) now have `725bc4b`+`977f492`'s
  evidence to score against; Performance (PENDING on the gauntlet) now has
  the gauntlet's numbers, and they are bad — score in whichever direction
  the evidence points, do not assume the direction. Full ranking of what the
  gauntlet found: ROADMAP "Current focus" — interaction cost (55-73s/face
  pick, 46-51s/edit) ranks first, ahead of the mesh payload and the
  round-trip drift. **Board queue length: 183 → 201 open
  items** (`grep -c '\[ \]'`-counted) — this pass closed 3 headline items
  (SCRIPT-1, F1+F2, CRAFT-13) and filed 16 (four PERF-REAL/gauntlet items,
  four code-review P1/P2 items, four Assemblies-wave items from
  DIRECTION-ASSEMBLIES.md, and four smaller process items — GEN-CHECK-
  VERDICT-1, DOCS-EXPLORER-1, CSP-1, AREA-INTEGRATION-1) net of one removed
  duplicate (the old flat-BOM entry BOM-ASM-1 replaces) — a filing-heavy
  pass, consistent with "a batch this large surfaces more findings than it
  closes." ROADMAP
  "Current focus" reconciled to match; Phase 5 marks the scripting API ✅,
  MCP server remains the open surface.

- **Groom pass 24 (2026-09-15, backlog-groomer) — Wave 3 CLOSED.** CRAFT-9a
  (`1f32a67`), CRAFT-9b (`11a0906`), CRAFT-10 (`7ecc480`+`894c6f3`) and
  CRAFT-11 (`c0b5e5f`+`0c707b9`) all ticked CLOSED, plus a cross-cutting
  Save-during-autosave fix (`d227843`). Nine gauge mounts now ship across
  seven verbs, every one with a live preview. Filed six new items from the
  wave's own findings (CRAFT-12..17: camera never re-fits on a preview,
  gauge/panel desync possibly sharing a root cause with the craft9b-gauges
  contract-β intermittent, `ToolButton` disabled-vs-busy audit, 3/12
  pre-existing unreachable edge points, the shell rim-vs-centroid seat
  decision, `gaugeReach.ts`/`gaugeProbe.ts` DRY convergence); GAUGE-TOUCH-1
  updated to cover all nine mounts and explicitly noted as a still-open
  W3-exit QA gate even though the wave itself is closed on the board this
  pass — a stated tension, not a silent resolution. CRAFT-9c stays Ready,
  now first in line. **Phase 5 (agent-native & extensibility) opened** —
  the public Python scripting API is in flight (see ROADMAP "Current
  focus" for the full rationale: it and the MCP server are one
  architecture flipping two ❌ scorecard rows, Extensibility + Agent
  access). Doc-tick debt measured: **12** commits since the last
  `docs(board)` commit (`bd1e05a`), none touching ROADMAP/BACKLOG — larger
  than pass 23's 4, all from Wave 3's remaining four gauge mounts landing
  in worktrees while two builders stayed live; reconciled in full this
  pass. **Board queue length: 183 open items (`grep`-counted), roughly flat
  from 181 last pass** — this pass closed 4 (CRAFT-9a/9b/10/11) and filed 6
  (CRAFT-12..17), consistent with the wave-close pattern: findings surface
  fastest right at the end. No scorecard row flips this pass (flow/craft
  items; Phase 5's own flips are ahead of us, not behind). ROADMAP "Current
  focus" reconciled to match.

- **Groom pass 23 (2026-09-14):** CRAFT-7's blocking finding fixed and
  closed; CRAFT-9a/9b/10/11 unblocked and dispatched. Filed
  GAUGE-PROPORTION-1, FORMATANGLE-MIGRATE-1, IMPERIAL-LADDER-1,
  GAUGE-TOUCH-1. Full detail: `docs/CHANGELOG.md`.

- **Groom pass 22 (2026-09-14):** board was stale (CRAFT-7 listed planned
  after shipping); ticked CRAFT-7/8, filed ESLINT-HOOKS-1,
  EXTRUDE-RAIL-ESCAPE-1, CRAFT-INTERMITTENT-1. Full detail:
  `docs/CHANGELOG.md`.

- **Groom pass 21 (2026-09-13):** cross-wave QA (`debfea2`) found one
  regression + three collisions, all seven fixes ticked; filed
  CUBE-SKETCH-OCCLUDE-1. Full detail: `docs/CHANGELOG.md`.

- **Groom pass 20 (2026-09-13):** reconciled the wave log onto BACKLOG; filed
  six items (MINIO-LICENSE-REVIEW-1 + five more). Full detail:
  `docs/CHANGELOG.md`.

- **Groom pass 19 (2026-08-29):** CI-4's original question ANSWERED (shard
  3/4 was structurally overloaded, not systemic instability); K2, PBT-1,
  SOLVE-CRASH-1, ARC-DEGENERATE-1 all closed. Full detail: `docs/CHANGELOG.md`.

- **Prior passes (8-18):** reconciled in `docs/CHANGELOG.md` / Done archive.
  Still true and still open: `docs/GEOMETRY-QA.md`/`docs/UI-REVIEW.md` are
  stale against the last nine batches — dispatch `geometry-qa` and
  `frontend-qa` next batch.

## Ready (top of queue)

**Dispatch order, groom pass 27 (2026-09-23) — every known e2e failure on
this branch (pass-26's 9 cases + the `f9fcce6`/`5444fa8` regression) is now
diagnosed and fixed LOCALLY (see ROADMAP "Current focus"); CI verification
is owed before new feature work resumes.** Once CI confirms the branch
clean: PERF-REAL-1 (now
PARTLY addressed, see below — re-measure before re-ranking it),
PERF-REAL-2, and the new product-audit findings (PICK-PROXY-COLLIDE-1,
EDGE-RESOLVE-WARN-1, MEASURE-LABEL-PITCH-1) lead — correctness/interaction-
cost risk still outranks craft polish. Ranked, disjoint,
parallel-dispatchable; MINIO-LICENSE-REVIEW-1 and CUBE-SKETCH-OCCLUDE-1 are
both decisions before they are build tasks — the first to the licensing
custodian/founder, the second may need founder/vision-steward input on the
options before a builder picks one:

1. [ ] (P1, M) **PERF-REAL-1 — 55-73s to select one face, 12.6-14.7s to open a
   real imported part.** kind: defect (interaction cost, frontend/viewport).
   MEASURED by `just gauntlet` on `gearbox-11752` (1018 faces): arm face-pick
   → prompt visible 40.8s/30.0s (two runs); click → prompt cleared 31.6s/24.6s
   — 55-73s total against 0.6s to reach "Pick a plane" in the first place.
   Pick-node census: 452 DOM overlay nodes for one part, 17.5s to settle them
   (bit-identical structural counts across two runs at different load, which
   is what makes this a real cost rather than an artefact). Ranked #1 by
   "what a user feels" in `docs/GEOMETRY-QA.md`'s gauntlet entry — nothing
   else on that list matters if the tool cannot be touched.
   **PARTLY ADDRESSED this pass by `9083f0a` (found while landing
   PickMark's depth `instanceof` fix, not dispatched against this ticket
   directly): drei's `Html` was calling `ReactDOM.createRoot` PER pick mark,
   so 452 marks were 452 independent React roots — ~13s of main-thread
   script, a hang rather than a slowdown. Now one portal host, one root, one
   per-frame projection pass: 3.5x faster per mark in a real browser and
   FLAT instead of super-linear in N (measured at N=113/452/904, all
   ~0.30ms/mark against 1.08-1.32ms before).** The 55-73s / 17.5s-settle
   figures above are NOT re-measured against this fix and are now an UPPER
   BOUND — `docs/VISION.md`'s Selection & picking row says so explicitly.
   ACCEPTANCE, updated: re-measure `just gauntlet` on `gearbox-11752` first
   (this may already materially close the ticket); if the settle time is
   still an order of magnitude off, the remaining lever is a different pick
   mechanism (canvas raycast instead of per-face DOM overlay) rather than
   further portal-host tuning. State the before/after numbers; do not
   declare victory on a toy part. [src: geometry-qa gauntlet,
   `docs/GEOMETRY-QA.md` 2026-09-15; progress `9083f0a`, groom pass 26]
   TERRITORY: `apps/web/src/viewport/**` (face-pick overlay). agentType:
   frontend-builder.

2. [ ] (P1, M) **PERF-REAL-2 — an incremental edit anywhere in a long feature
   tree costs a full rebuild.** kind: defect (perf, kernel). MEASURED at 250
   features: repeat 235ms, append 2444ms, edit feature #249 (near the end)
   45955ms, edit feature #3 (near the start) 48449ms, cold rebuild 51741ms —
   an edit costs 89-108% of a full cold rebuild WHEREVER it sits in the tree,
   confirmed load-invariant by re-measuring at a different load average (the
   edit/cold RATIO moved from 0.89/0.94 to 1.02/1.08, i.e. it did not improve
   under less contention). `rebuild_cache.py` already documents that it does
   not serve a mid-tree edit; this gives the gap a number on a realistic
   part: ~46-51s for a one-parameter change. Ranked #1 (tied with
   PERF-REAL-1) in `docs/GEOMETRY-QA.md`'s gauntlet ranking. ACCEPTANCE: a
   checkpoint ladder (intermediate cached states at more than just the
   cache's current frontier) measurably reduces edit cost for an edit near
   either end of a 250-feature tree, with the new number and the old number
   both stated. Do not regress `repeat`/`append`'s existing near-zero cost.
   [src: geometry-qa gauntlet, `docs/GEOMETRY-QA.md` 2026-09-15] TERRITORY:
   `services/geometry/src/geometry/kernel/rebuild_cache.py`. agentType:
   kernel-architect.

3. ~~**VEC3-DEDUP-1**~~ — **CLOSED (`4549da8`, groom pass 26).** See closure
   note below, after this numbered list.

4. [ ] (P1, S) **CONTRACT-PARITY-TEST-1** — the call-parity test
   `packages/loft-script/src/loft/transport.py` documents as closing the
   loop does not exist. kind: defect (missing gate, not a live bug — SCRIPT-1
   follow-up). `transport.py:148-156` states the model passed to `call()` is
   never looked up from `operation.response_model` "on purpose ... the
   contract-parity test closes the loop by asserting the two agree for every
   call site" — but `test_contract_parity.py`'s five tests only assert that
   `response_model` NAMES resolve to contract components, never that any
   `transport.call(op, Model)` site passes the Model the contract declares
   for that op. AST-walking the 16 call sites by hand today finds 0
   mismatches, so this is not yet a live defect — but Pydantic's
   `extra="ignore"` default means a structurally-compatible WRONG model
   validates silently (CLAUDE.md's own documented trap), and the docstring
   claims a guarantee nothing enforces. ACCEPTANCE: ~25 lines of `ast` in
   `test_contract_parity.py`, with a count floor (`len(sites) >= 16`) so it
   cannot pass by walking nothing; mutation-verified to redden when a call
   site's model is swapped for a wrong-but-compatible one. Also confirm with
   the author whether `part.py:317`'s `call_none` on a DELETE that declares a
   `response_model` (discarding the fresh tree, then issuing a second
   `refresh()`) is deliberate. [src: code review P1-3, `docs/CODE-REVIEW.md`,
   `451245c`] TERRITORY: `packages/loft-script/tests/test_contract_parity.py`.
   agentType: backend-builder.

5. [ ] (P1, S) **MINIO-LICENSE-REVIEW-1** — MinIO is AGPL-3.0 and has no entry
   in `docs/LICENSING.md`; needs a human/licensing-custodian decision, not an
   automated one. kind: question (licensing/compliance). `docs/RESEARCH.md`
   §8: "Forbidden: GPL/AGPL dependencies. Reviewers enforce this."
   `docs/LICENSING.md` carries 72 entries and none for MinIO. Orchestrator's
   own reading, NOT adjudicated here: likely NOT a violation as shipped
   today — MinIO runs as a separate process over the S3 HTTP API, we do not
   link, modify or redistribute its bytes, so it reads as aggregation, and
   AGPL §13's network clause binds whoever DEPLOYS it. But §8's own amendment
   holds "`docker push` is what makes us a distributor," and `bd58416`
   (2026-09-13) had to repoint our compose pins because MinIO Inc. withdrew
   ALL binary images and moved to source-only distribution — so if upstream
   never publishes binaries again, the replacement path may require building
   the image ourselves, which is the scenario that amendment exists for.
   ACCEPTANCE: a licensing-custodian pass (or founder decision) records a
   verdict in `docs/LICENSING.md` — either "aggregation, no entry needed,
   here is why" or "here is the entry, and here is what changes if we ever
   build our own MinIO image." Do not resolve silently either way. [src:
   orchestrator, `bd58416` follow-up, 2026-09-13] TERRITORY:
   `docs/LICENSING.md`, `docs/RESEARCH.md` §8. agentType: oss-curator /
   founder decision.

6. [ ] (P2, M) **FLOW-JOURNEY-GAP-1** — the canonical part-creation journey
   does not exercise the shortcuts W2 shipped, so `scripts/check-flow-cost.py`'s
   headline (30 gestures) is unchanged and the wave's win is unmeasured on the
   path anyone actually walks. kind: capability/measurement. FOUND: the
   script's only "no API shortcuts" journey is `full-flow.spec.ts` (register
   → part → sketch → extrude → edit → export), which still drives the
   toolbar for every verb — K/E/R/F/C (FLOW-B2), the solved-sketch Extrude
   chip (FLOW-B1) and the next-verb accent (FLOW-B3) are all reachable from
   that same journey and none are used. WHY IT MATTERS: W2 made a shorter
   path EXIST; nothing made it the path the measurement — or a new user —
   takes, so the metric the loop steers by cannot see whether the wave paid
   off. ACCEPTANCE: either (a) a second canonical-journey spec that uses the
   accelerators + chip + accent end to end, with `check-flow-cost.py`
   reporting BOTH numbers (toolbar-path vs. accelerated-path) so the delta is
   visible and honest, or (b) the existing journey updated to take the
   shortest correct path with a documented reason for any step that must stay
   toolbar-driven. Regression: the toolbar-only number must not silently
   disappear. [src: FLOW-B1/B2/B3 integration, orchestrator report,
   2026-09-13] TERRITORY: `scripts/check-flow-cost.py`,
   `apps/web/e2e/full-flow.spec.ts` (or a new sibling spec). agentType:
   frontend-builder.
   **ADDENDUM, groom pass 23 (stated prediction, not a new regression):** the
   30-gesture number will not move for the WHOLE of Wave 3, on any pass, and
   that is not grounds to distrust the metric — `--journey fillet` reads 3
   gestures today and a gauge version also reads 3. The metric models an
   expert who already knows every verb; it is structurally blind to what W3
   buys, which is legibility for an engineer who does not know what 5 mm of
   fillet looks like on THIS part until they drag it and see (same gesture
   count, forty seconds versus two). W3's real evidence is screenshots,
   per-verb reach counts and the contract-β release test, not this number.
   [src: DIRECTION-W3-PROPOSALS.md §12 / groom pass 23 dispatch brief]

7. [ ] (P2, M) **GRIDMINOR-TONEMAP-1** — grid minor lines are ~invisible, and
   the direct fix reddens a neighbouring gate. kind: defect (visual craft,
   cross-gate tension). FOUND (CRAFT-1/2/3 agent, correctly reverted rather
   than shipped): `gridMinor` (#232E3C) reaches the canvas at ~(21,26,33),
   within 3 luminance units of the background, because the tone mapper
   re-grades it before the pixel lands. Un-tone-mapping the grid line fixes
   the contrast but reddens `part-visibility.spec.ts`'s ghost census (203
   against a 131 ceiling): the canvas is premultiplied-alpha and drei's grid
   shader emits straight colour, so the readback amplifies grid pixels past
   the specular threshold used to detect a ghosted body. NOT in CRAFT-2's
   scope (that item was the ortho ground plane, already shipped).
   ACCEPTANCE: grid minor lines measure a contrast delta against the
   background consistent with the major lines' own ratio (state the number),
   AND `part-visibility.spec.ts`'s ghost census stays under its existing
   ceiling — fix the census's colour-space assumption (premultiplied vs.
   straight) rather than trading one gate's pass for the other's fail. [src:
   CRAFT-1/2/3 agent measurement, 2026-09-13,
   docs/design/AUDIT-CRAFT-2026-09.md] TERRITORY: `apps/web/src/viewport/**`
   (grid material/tone-mapping), `apps/web/e2e/part-visibility.spec.ts`.
   agentType: frontend-builder.

8. [ ] (P2, M) **MODALGATE-MIGRATION-1** — `modalGate`/`useModalLayer` is
   built as "one gate, not a patch per listener" but still has only TWO
   registrants against 22 named holdouts. kind: defect (systemic, incomplete
   rollout — same shape as REASON-GATE-1's "15 of 16 editors" finding).
   **PROGRESSED, not closed, since filed:** `6602ccd` (W2 review) gave
   `ShortcutSheet` (the key card) a registration — the exact "`? then E`
   opens Extrude behind the card" defect this ticket predicted — plus an
   `activationKeyOwner` seam so a focused button's own Enter/Space is no
   longer stolen, and a leak alarm that fires the instant a key reaches the
   workspace while an `aria-modal="true"` element is on screen.
   `modalGate.audit.test.ts` now WALKS `apps/web/src` for raw
   `addEventListener("keydown")` and names every file not in its table: 22
   pre-seam listeners across 12 files, recorded but not migrated. That audit
   test is the acceptance-criteria enumeration this ticket asked for — read
   it for the remaining list rather than re-deriving one.
   ACCEPTANCE: migrate the 22 named listeners onto `useModalLayer`/
   `modalGate` (or the `activationKeyOwner` seam, whichever applies), each
   with the same alarm-probe coverage `da98622` gave the first registrant. A
   regression test proves a stray key while ANY registered layer is open
   cannot reach the sketch behind it. [src: brief item 7 / da98622 follow-up,
   2026-09-13; progress `6602ccd`, W2 review, 2026-09-13] TERRITORY:
   `apps/web/src/lib/modalGate.ts`, plus the 22 files named by
   `modalGate.audit.test.ts`. agentType: frontend-builder.

9. [ ] (P2, S) **AXISLABEL-ORTHO-1** — `origin-axis-label-{X,Y,Z}` are absent
   from the DOM in front-orthographic when datums are enabled, though present
   and visible in the default view. kind: defect. Found during CRAFT-1/2/3
   verification; view-dependent, uses drei `Html`, not caused by that diff
   and not yet root-caused. ACCEPTANCE: reproduce first on current HEAD; with
   origin/datums enabled, switch to front-orthographic and assert the three
   axis-label elements are present in the DOM at the same measured presence
   as the default view. If a legitimate reason exists for a label to retire
   in that view, state it and gate the absence deliberately instead of
   leaving it unexplained. [src: CRAFT-1/2/3 agent measurement, 2026-09-13]
   TERRITORY: `apps/web/src/viewport/OriginGeometry.tsx` (or wherever axis
   labels are drawn). agentType: frontend-builder.

10. [ ] (P2, S) **VIEWFRONT-ORTHO-DECISION-1** — `view-front` (and the other
   named views) silently switch the camera to orthographic; decide this on
   purpose rather than by inheritance. kind: question (product decision).
   `viewCommands.ts`: the first named view the modeler asks for switches
   projection — so pressing `1` was, until CRAFT-2 landed, the fastest route
   into the empty-ground-plane bug (front/right/top ortho had no ground at
   all). CRAFT-2 fixed the symptom; this ticket is whether a named-view key
   SHOULD carry a projection change as a side effect, or whether view and
   projection should be independent controls (as CRAFT-6 already argues for
   the cube vs. the projection control during authoring, for a related
   reason). ACCEPTANCE: a decision recorded in
   `docs/design/REDESIGN-ROADMAP.md` or `docs/VISION.md` with its reasoning;
   if named views keep the ortho side effect, `view-projection`'s own
   affordance must not contradict it; if decoupled, `viewCommands.ts` changes
   accordingly with a regression test. Relevant to CRAFT-21 (Home restores
   projection; ViewCube re-fits) — coordinate so the two do not re-litigate
   the same seam twice. [src: CRAFT-1/2/3 agent finding, 2026-09-13]
   TERRITORY: `apps/web/src/viewport/viewCommands.ts`. agentType:
   frontend-builder (decision may need founder/vision-steward input first).

11. [ ] (P2, M) **CUBE-SKETCH-OCCLUDE-1** — full ticket in the wave log above
   (this pass's cross-wave QA finding). A product decision on whether the
   reference cube's pick-armed pointer-yield (`d0a3190`) should extend to
   ordinary sketch drawing, not just armed picks.

12. [ ] (P1, M) **CRAFT-9c — now leads the Ready queue.** Hole depth + Ø
   gauges, the only `companion` two-cell gauge in the wave. **Deliberately
   NOT dispatched alongside CRAFT-9a/9b/10/11** — DIRECTION-W3-PROPOSALS.md
   §8.3 sequences it last, once the tag/`companion` shape has settled from
   the other four, now all CLOSED (CRAFT-7's own follow-up found `companion`
   had shipped narrowed to
   `Pick<GaugeCell, "tagLabel"|"value">`, losing the per-cell `track` §6.1
   specified for a mixed-unit pair — fine for hole today since depth and Ø
   are both mm, but the shape this item inherits should be checked once
   CRAFT-9a/9b/10 have exercised it). `linear` track, anchor on the hole
   axis. ACCEPTANCE: same as CRAFT-9a/9b (drag/arrow-key/reach/contract-β)
   plus a companion-cell check — dragging depth does not move the Ø cell's
   own displayed track and vice versa. §8.4 preview gate: the bore circle
   and the depth plane, or defer to W5. [src: DIRECTION-W3-PROPOSALS.md
   §8.3/§9] TERRITORY: `apps/web/src/viewport/**` (gauges),
   `apps/web/src/components/HoleEditor.tsx`. agentType: frontend-builder.

~~**CRAFT-12-READPROPOSAL-1**~~ — **CLOSED (`5274bea`), same day as filed.**
    `readProposal` returned the whole `command-layer` group's world box;
    annotation roots (SketchScene, MeasureOverlay, EdgePickOverlay,
    FacePickOverlay, ShellFaceOverlay, HolePointOverlay,
    BendHighlightOverlay, FlangeSpanOverlay) now carry a tag `proposalBoxOf`
    skips. Measured both directions on the fixture this ticket cited: a
    resting sketch 100 mm away no longer triggers a re-fit on gauge release
    (297.0 mm camera travel -> 5.5 mm, the residual being a LEGITIMATE
    re-fit — the arrow itself pokes past the already-filled frame); a
    genuinely out-of-frame proposal (10 mm body, 300 mm extrude) still
    fires (550.5 mm travel). 5 new unit cases, each verified to redden
    under a mutant.

14. [ ] (P1, M) **PICK-PROXY-COLLIDE-1 — pick proxies collide with each
    other and with the gauge; the collisions are systematic, not random.**
    kind: defect (selection, frontend). MEASURED with `elementFromPoint` at
    each proxy's own centre, on a real gearbox-housing part: Measure draws
    **110 proxies (66 edges + 44 vertices) at once, 48 of them (44%)
    unreachable at their own centre** — each other's collisions; Fillet's
    `fillet-radius-sleeve` (88x17) lands exactly on `edge-pick-4`, so the
    gauge that appears when you pick covers one of the things you pick;
    Hole's inner-wall proxy sits 9px from the outer wall's twin and resolves
    to it; Shell's `shell-face-1` (bottom face) is drawn at a screen point
    inside the visible FRONT wall, so clicking the middle of the front wall
    opens the bottom and the panel reports "1 face open" with no warning.
    The GL raycast rescues most picks (decided in 3D, not by the DOM
    stack), but the DRAWN markers are what a user aims at and they lie
    about what is under them. ACCEPTANCE: a documented minimum separation
    between simultaneously-drawn proxy centres (or a "select other" cycle
    for coincident candidates, matching PICKMARK-OCCLUDE-1's precedent for
    edges), verified on the same fixture class (a part dense enough to
    produce >=40 proxies at once); the gauge/proxy overlap on Fillet is a
    P0-shaped sub-case (a picked edge becomes un-unpickable) and should be
    fixed first if the full census is too large for one slice. [src:
    AUDIT-PRODUCT.md F-4, 2026-09-16 pass] TERRITORY:
    `apps/web/src/viewport/{EdgePickOverlay,FacePickOverlay,
    ShellFaceOverlay,HolePointOverlay,PickMark,MeasureOverlay}.tsx`.
    agentType: frontend-builder.

15. [ ] (P1, S) **MEASURE-LABEL-PITCH-1 — Measure gives a number an
    engineer will act on and get wrong.** kind: defect (product/measure).
    MEASURED: picking two adjacent Ø8 holes of a pattern whose
    centre-to-centre pitch is **25 mm by construction** reads back
    `DISTANCE 17 mm` (25 − 8, the minimum circle-to-circle distance) with
    no label saying "minimum" and no centre-to-centre / diameter / radius
    option on a circular edge — hole pitch is the single most common
    measurement taken on a plate, and Fusion defaults two circular edges to
    centre-to-centre. Edge labels are also identity-free (`"Edge 5,
    circle"`, no coordinates), so there is no way to tell which two holes
    were measured after the fact. ACCEPTANCE: picking two circular edges
    offers (at minimum) a centre-to-centre reading, labelled as such and
    distinct from the raw minimum-distance reading; edge labels carry
    enough identity (coordinates or a stable name) to reconstruct which
    entities were measured from the readout alone. [src: AUDIT-PRODUCT.md
    F-7, 2026-09-16 pass] TERRITORY: `apps/web/src/measure/**`,
    `services/geometry/src/geometry/**` (if centre-to-centre needs a new
    measurement kind on the wire). agentType: frontend-builder
    (backend-builder if a new measurement kind is needed).

16. [ ] (P1, M) **EDGE-RESOLVE-WARN-1 — a feature needs a warning channel
    before partial/best-effort edge resolution is safe to leave silent.**
    kind: defect (trust/observability, backend + frontend). `docs/design/
    topological-naming.md` §7.3 has always been explicit that stage-1
    matching (which adjacency tier 3, `bf05482`, is one more tier of) is
    **best-effort and can silently mis-resolve** — a lone wrong match after
    a move is a documented, accepted residual, not a bug. Nothing in the
    product today tells the modeler when this happened: a feature that
    rebuilds via a best-effort tier reports exactly the same `OK` as one
    that resolved on an exact match, so a silently-wrong pick (the wrong
    edge, on a part with several similar ones) looks identical to a correct
    rebuild until someone notices the geometry is off. This is now sharper
    with tier 3 live: it "inherits the face matcher's best-effort §7.3
    posture WHOLESALE, including its silent-retarget surface" (bf05482's
    own commit message). ACCEPTANCE: the evaluator records WHICH tier
    resolved each subshape reference (exact / durable / adjacency-assisted)
    in the feature's rebuild result; the frontend surfaces a visible,
    dismissable notice (tree row + banner, matching the existing
    `SUBSHAPE_UNRESOLVED` vocabulary) when a feature rebuilt on anything
    less than an exact match, naming the feature and the tier. Do not block
    the rebuild — this is a warning channel, not a refusal. [src:
    `docs/design/topological-naming.md` §7.3, `bf05482`, groom pass 26]
    TERRITORY: `services/geometry/src/geometry/{features,kernel}/**`
    (evaluator result), `apps/web/src/routes/PartPage.tsx` (tree row
    surfacing). agentType: kernel-architect + frontend-builder (split into
    a backend slice landing the tier-on-the-wire field, then a frontend
    slice surfacing it).

17. [ ] (P3, XS) **INSTANCEOF-THREE-1 — 15 `instanceof` sites against
    three.js classes are latent in the shipped app and will break any new
    Viewport unit test.** kind: defect (test-infra hazard, not a live
    product bug). `three@0.185.1` ships dual ESM/CJS builds from one
    version, so `instanceof PerspectiveCamera` resolved through `require`
    is a DIFFERENT class object than one resolved through `import` — no
    version skew, no lockfile fix possible. MEASURED: exactly one `three`
    is installed and only `apps/web` depends on it, so the shipped Vite
    bundle has a single module graph and all 15 sites (12 in
    `Viewport.tsx`, plus `SketchScene.tsx`, `BenchBackdrop.tsx`,
    `glbGeometry.ts`) are CORRECT today — this is not a live defect. It
    bites in `vitest`, where `@react-three/fiber` resolves to its CJS dev
    build and pulls a second module record of `three`: probed against a
    real r3f root, `isPerspectiveCamera: true` while
    `instanceof PerspectiveCamera: false`. So the moment anyone writes a
    unit test for `Viewport.tsx`'s camera logic, all 13 of its sites will
    fail inexplicably, reading as a broken mock rather than a test-
    environment module-duality quirk. ACCEPTANCE: migrate the 15 sites to
    three's own duck-typed flags (`isPerspectiveCamera`,
    `isOrthographicCamera`, `isMesh`, etc. — true across every copy, cost
    nothing), OR at minimum document the trap inline at each site so the
    first unit-test author does not lose a debugging session to it. Grep
    the CALL (`instanceof `) not a class name — `instanceof` against a
    browser/JS builtin (`HTMLElement`, `Error`, etc.) is fine and out of
    scope. [src: `docs/CLAUDE.md` environment recipe, `89d4d4d`+`dbddb17`,
    groom pass 26] TERRITORY: `apps/web/src/viewport/Viewport.tsx`,
    `SketchScene.tsx`, `BenchBackdrop.tsx`, `glbGeometry.ts`. agentType:
    frontend-builder.

18. ~~**CRAFT12-OUTWARD-ONLY-1**~~ — **CLOSED (`202cc9d`, groom pass 27).**
    Root-caused: the bimodal pull was the preview re-fit ITSELF (not a
    second bounds-driven fit) — `frameOverrun` was a FIT ratio
    ("would a frame CENTRED ON THE ORBIT TARGET hold the subject") fed to a
    pose that deliberately parks the target OFF the subject
    (`targetShift`), so after a shrink the two disagreed and a second,
    spurious re-fit fired on the shrink itself. Fixed by projecting each
    corner exactly as the renderer will and returning distance from the
    FREE-RECT centre as a fraction of half-extent — `<=1` is on screen by
    construction, and a smaller subject cannot read larger, so "outward
    only" is now arithmetic, not a race. 10/10 held (was 6/11 pulled in
    15.7x); unit: 5 of 22 cases redden against the old ratio.
    [src: `f8a1ecb`, groom pass 26; closed groom pass 27]

19. ~~**CONSTRAINTS-GLYPH-1280-1**~~ — **CLOSED (`5444fa8`, same pass it was
    filed in).** Root cause: at 1280x800 a canvas click DRAWS while
    sketching (unlike the part workspace, where it orbits/selects), and
    `f9fcce6`'s Fit control sat on the bottom-centre seat the sketch rig's
    own -Y axis projects through at plane (0,-55) — `elementFromPoint`
    there resolved to `sketch-view-fit`, so the spec's centerline click
    became a Fit instead of a line start and the symmetric glyph never
    drew. Fixed by seating the sketch Fit bar off the LEFT edge of the
    reference cube's own box (same `*-view-cube` tokens, no new numbers),
    off both sketch axes. `constraints.spec.ts` 12/12 (was red at :1112),
    `sketch-fit.spec.ts` 3/3. Screenshots refreshed
    (`sketch-fit-{entry,after}-{1280,1440}.png`).

20. [ ] (P2, XS) **QA-CUBE-YIELD-SETTLE-1 — the sibling of `36360ae`'s fix,
    same file, same unfixed pattern.** kind: defect (test hardening).
    `qa-cross-wave-0913.spec.ts`'s "the cube is a control again once the
    pick is over" (now line ~592) clicks a cube facet, `await page.
    waitForTimeout(800)`, then compares `data-camera-pos` — the EXACT
    pattern `36360ae` (groom pass 27) fixed at this file's other cube-click
    case by polling `data-view` for the `direction` settle stamp instead of
    sleeping. Three agents have seen this case fail locally under load;
    CI has stayed green on it so far, which is consistent with the same
    load-sensitivity `36360ae` measured (7/7 red under load, 0/8 quiet) —
    triage before assuming either "load-sensitive timing gate" or "a real
    defect" without checking. ACCEPTANCE: apply the same settle-stamp poll
    (`onSettle` writes `data-view` when THIS click's ease lands); if it
    reddens under load first and passes after, that confirms the same
    class as `:253`; if it does NOT reproduce under load at all, say so
    and close as environment-only. [src: reported by three agents under
    load, filed by backlog-groomer pass 27; see CRAFT-INTERMITTENT-1 for
    the `:253` sibling's closure] TERRITORY:
    `apps/web/e2e/qa-cross-wave-0913.spec.ts`. agentType: qa-tester.

21. [ ] (P2, S) **FILLET-GAUGE-FPS-FLOOR-1 — the ">10 frames sampled after
    release" floor assumes ~6.7fps, which headless software GL misses
    under load, and it fails on a clean tree.** kind: defect (test
    hardening, needs an owner). `fillet-chamfer-gauge.spec.ts`'s contract-β
    case asserts `frames.length` (sampled over `RELEASE_WINDOW_MS`) is
    `toBeGreaterThan(10)` — a message-based floor on how many animation
    frames rendered, not on the property the case actually cares about
    (rod and field agree every sampled frame). MEASURED: reproduces on the
    unmodified base tree too (`357b91e`'s own evidence: "fails on the
    UNCHANGED tree too (1 of 8, received 9)"; `f9fcce6`'s evidence:
    "reproduces on the CLEAN base 37e6e18 too, wandering between the
    fillet and chamfer cases"). ACCEPTANCE: assert the property (every
    sampled frame agrees, however many there are; and separately, that at
    least one frame after release was sampled at all — the "window is
    vacuous" guard, which can stay a small floor since it is a sanity
    check, not a timing budget) rather than an fps-derived count; do not
    fix it by lowering the threshold, which only moves the load level at
    which it flakes. [src: reproduced independently by `357b91e` and
    `f9fcce6`, filed by backlog-groomer pass 27] TERRITORY:
    `apps/web/e2e/fillet-chamfer-gauge.spec.ts`. agentType: qa-tester.

22. [ ] (P2, S) **PATTERN-SCOPE-TIMEOUT-1 — two `pattern-scope.spec.ts`
    cases hit the 60s test timeout under load, on HEAD as well.** kind:
    defect (test hardening). "select Hole1, press Pattern, get six holes
    (not a six-times plate)" (line 324) and "a scoped pattern round-trips:
    re-opening it shows Hole1, not a guess" (line 530) both time out under
    CPU load without a code change implicated — same signature as this
    repo's documented quiet-window flake class (CLAUDE.md: "a real code
    regression fails identically every time; a contention flake wanders").
    ACCEPTANCE: instrument before guessing (per-phase timers, not a
    reflexive `expect.poll`/timeout bump) to find which step is slow under
    load — building the plate, drilling, or the pattern dialog itself —
    and fix or budget that step specifically; if the cost is legitimately
    higher under load (e.g. more geometry to rebuild), raise ONLY that
    step's timeout with the measured number stated, not the whole test's.
    [src: reproduced under load on HEAD, filed by backlog-groomer pass 27]
    TERRITORY: `apps/web/e2e/pattern-scope.spec.ts`. agentType: qa-tester.

~~**SCRIPT-1**~~ — **CLOSED (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`, groom
pass 25).** Public Python scripting API shipped; see wave log / ROADMAP
"Current focus" for the full proof (two-path-identical against a
browser-driven build, 12/12 facts, byte-equal STEP/STL hashes) and Done
archive for the record.

~~**CRAFT-12**~~ — **CLOSED (`7a15bea`, groom pass 26).** See wave log above
for the fix and the residual it surfaced — CRAFT-12-READPROPOSAL-1, filed
this pass and closed the same day (`5274bea`), see the Ready list below.

~~**VEC3-DEDUP-1**~~ — **CLOSED (`4549da8`, groom pass 26).** One
`packages/design/src/vec3.ts` replaces the four divergent copies
(`axisAnchor`/`edgeAnchor`/`faceAnchor`/`gauge.ts`); consolidation chose
`edgeAnchor`'s picometre-floor + `null`-refusal behaviour and closed a live
Infinity-into-NaN path (`scale(a, 1/Infinity)` passed every copy's own
floor guard). 44 e2e green, negative control reddens 9/17 new cases.

~~**CRAFT-13**~~ — **CLOSED (`b4e7821`, groom pass 25).** Root-caused: the
per-segment hit sleeve made band count a function of drag value, so a
shrinking arc sweep unmounted its own pointer-capture host mid-drag (a P0
found in the same investigation, also fixed); the `craft9b-gauges`
contract-β "intermittent" was the same release-desync shape, confirmed as
an unstated settle rather than a flake. See wave log for full detail and
Done archive for the record.

**Also ready, not yet dispatched (P2, full tickets in the wave log above):**
CRAFT-14 (`ToolButton` disabled-vs-busy audit), CRAFT-15 (3/12 pre-existing
unreachable edge pick points), CRAFT-16 (shell gauge rim-vs-centroid seat,
product decision), CRAFT-17 (`gaugeReach.ts`/`gaugeProbe.ts` DRY
convergence), GAUGE-TOUCH-1 (W3-exit touch QA gate, now covering all nine
mounts — still open, dispatch alongside Phase 5 work per its own note).

**Carried from groom pass 19 — no new P0 that pass; SOLVE-CRASH-1, K2, PBT-1,
CI-BAL, MEASURE-PROXY-1, PICKMARK-OCCLUDE-1, EXPORT-3, REACH-3-FLOW,
REACH-2-FLOW, A11Y-TOOLBTN-1, HEM-1C, HEM-1D, SEL-8 and PGTEST-GATE all
shipped that batch or the last (see Done archive). Nothing is in flight.**
Ranked, disjoint, parallel-dispatchable:

1. ~~**GATE-FLOOR**~~ **DONE 2026-08-29** — both named gates floored, and the
   sweep of the other three found two more holes (`check-build-context`'s
   MAIN path, `check-tailwind-scale`'s accidental `max()` floor). Residue
   filed as GATE-FLOOR-2 (P3).
2. ~~**MATEUI-1**~~ — **CLOSED 2026-08-29.** Rendering only: the diagnosis is
   already typed on the wire, so nothing in `services/geometry` changed. Mates
   now carry an `M1`/`M2` handle the message names and the panel shows; the
   "remove this one" action shipped in the same commit. See the entry below.
3. ~~**LAYOUT-1**~~ — **CLOSED BY MEASUREMENT 2026-08-29, no fix needed.**
   Does not reproduce on HEAD (band and strip abut at 0.0 px; the audit
   measured 73 px). T-18 + the density pass had already fixed it. A
   clip-aware regression gate ships in its place.
4. ~~**GHOST-1**~~ — **CLOSED 2026-08-29.** A body with no stop of its own
   now ghosts while a sketch is open, as a derived default; a stop the
   modeler set is never overridden or silently restored. Filed
   CAMRESTORE-1 (P2) from the measurement.
5. **STEPNAME-1 is PART-SHIPPED, and the headline half is NOT ours**
   (kernel-architect, 2026-08-29) — the geometry writer already carries the
   instance name; the UUID is the fallback for a request that omits it, and
   the caller that omits it is `apps/web`. Two REAL geometry defects found and
   fixed alongside (non-ASCII names corrupted; the file named build123d as its
   author). See the entry below; STEPNAME-1B was the remaining web half and is
   closed. **STEPNAME-2 is closed too (2026-09-04)** — the single-body export
   carried both of those defects on the MORE common path, and now writes through
   the same owned writer, proved byte-identical to build123d's output so no
   file's shape and no golden's hash moved.
6. **ARC-DEGENERATE-1 is SHIPPED** (kernel-architect, 2026-08-29) — 27 of
   2000 payloads were shipping an arc collapsed onto its own centre, at a
   residual of zero; now `sketch_conflicting` with the constraint named. See
   the entry below and ROADMAP for the census and the two follow-ups filed.
7. ~~**HEM-1B**~~ — **CLOSED 2026-09-04.** The gated Save states its reason and
   an override toggle seeds its own field, so the audit's checked-and-empty dead
   end cannot be clicked into. The reported hydration bug did NOT reproduce at
   HEAD (measured: `k_factor: null` already loads unchecked). Filed
   **REASON-GATE-1 (P1)** from the survey it asked for: 15 of the 16 editor
   commit actions have the same silence, while 41 of 43 toolbar tools do not.
   ~~**REASON-GATE-1**~~ — **CLOSED 2026-09-04.** All seventeen say why, from one
   computation (`canSubmitX` is DEFINED as `blocker === null`), and all seventeen
   action rows moved into the pinned footer — a second unfinished rollout found
   in the same files, and the one that made the sentence legible at 1280x800.
8. **SNAP-4** (P2, S, frontend-builder) — an explicit Fix on a point the
   draw already grounded misreports OVER-CONSTRAINED.
9. **REACH-2-FLOW-C** (P2, M, frontend-builder) — the feature tree has no
   select-without-editing gesture, and the command band is out of room at
   1280.
10. ~~**MATE-OBS-2**~~ — **CLOSED 2026-08-29.** `mateErrors` moved onto
    `AssemblySolve` (empty whenever stale) and the panel takes `solve`, not the
    raw evaluation, so there is nothing ungated left to read; the matrix gained
    it as an eighth case with a non-vacuity settled branch. See the entry below.

**Also ready, not yet dispatched:** QA-R3 (P2, touch — harness gap filed as
PLAYWRIGHT-TOUCH-1), NAME-2b (P2), TITLEBLOCK-STAMP-1 (P2, XS),
SKETCH-COVERAGE-1 (P2), STAGE-DOC-HUNKS-HEADING-1 (P2), SOLVE-CONFLICT-MOVED-1
(P2, XS), SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (P2, S),
CHECKUIPARITY-FP-1 (P3), NUDGE-PLACEMENT-QUANTISE-1 (P3), SOLVER-DOC-1 (P3,
XS), SHARD-MANIFEST-CI-1 (P3, new this pass) — see full tickets in place.

**Process/loop-health flag, carried six passes now:**
`docs/GEOMETRY-QA.md`/`docs/UI-REVIEW.md` are stale against the last eight
batches — dispatch `geometry-qa` + `frontend-qa` next batch; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check is overdue (six passes).

Everything else below is reprioritized but not yet dispatched this batch.

**SPEC-10 and SNAP-5 are both SHIPPED (`42f6bbd`, `ecdf9ad`+`31ba716`) — see
Done archive for evidence/gates.**

**SKETCH-VOCAB-1 is fully SHIPPED (`38e37f5`, groom pass 15) — see Done
archive for evidence/gates.**

**MATE-1 is CLOSED (`a2a6f9f`, gate `1ae3270`, groom pass 15) — see Done
archive for evidence/gates. T-13 closes with it. T-14 (a different
surface) does NOT — re-filed narrower below.**

**MEASURE-PROXY-1 is CLOSED (2026-08-28, frontend-builder) — the occluder was
drei `Html`'s own wrapper div, not a coincident face (Measure has no faces); 5
marks on a bare box -> 0 after `PickNode` opted back in, `viewport/PickMark.tsx`.
See Done archive.**

- [ ] (P2, S) **NAME-2b — the durable-tier re-match NAME-2 shipped
      resolves silently; surface it on `FeatureResult` so an edge-anchored
      feature can show the same `RE-ANCHORED … CONFIRM` chip the drawings
      module already shows for dimensions.** kind: capability
      (observability, not correctness — the kernel resolver already
      returns the current signature + tier, per `c2700ee`'s own note: "a
      client can heal the reference — surfacing that on FeatureResult is a
      py-kit + web change, not a kernel one"). FIX: thread the resolver's
      tier through `FeatureResult` (py-kit schema + gateway pass-through)
      and render the existing `RE-ANCHORED` chip / anchorHeal affordance
      (`apps/web/src/drawing/anchorHeal.ts`'s pattern) on feature-tree rows
      whose tip subshape resolved on the tolerant tier, not just on
      drawing dimensions. ACCEPTANCE: an edge-anchored fillet/chamfer/edge
      flange that resolves via `resolve_edge_durable`'s tolerant tier shows
      the chip in the tree panel; a strict-tier resolve shows nothing
      (regression guard — no chip noise on the common case).
      [src: `docs/design/topological-naming.md` §13 (`c2700ee`'s own
      follow-up note), filed by backlog-groomer pass 13]
      TERRITORY: `packages/py-kit/src/py_kit/schemas/features.py`,
      `services/gateway/**` (pass-through), `apps/web/src/routes/
      PartPage.tsx` / tree panel. agentType: backend-builder +
      frontend-builder.

- [x] (P2, S) **ARC-DEGENERATE-1 — SHIPPED (kernel-architect, 2026-08-29).
      27 of 2000 payloads shipped an arc collapsed onto its own centre, and
      every gate agreed with all 27.** The asymmetry the ticket named was the
      only signal there was: a `SketchArc` derives its radius from three
      coordinates, so an annihilated one is a valid DTO whose residual is
      *zero* — a constraint satisfied by putting a point on a point is
      satisfied exactly. Population measured before choosing a fix, per the
      ticket: 25 `overconstrained`, 2 `underconstrained`, all at 4e-14 mm or
      less. Prior question re-asked (pin a reachable radius; re-solve from 8
      pushed starts): **26 forced, 1 branch**; 16 of the 26 minimise to a
      single `coincident` between an arc's own centre and its own endpoint —
      literally the input shape `_add_entity` refuses, authored as a
      constraint. Fix is SOLVE-CRASH-1's with no new machinery
      (`_shippable_arc_points` -> the existing payload gate ->
      `sketch_conflicting`, constraint named); the input refusal keeps its
      exception but is now the same magnitude test rather than `== 0.0`.
      **The floor is NOT the circle's** — an arc's radius is a derived
      distance, not a solver parameter, and the fix's own effect on the settle
      moved trial 458 to 4.5e-9 mm, above `DEGENERATE_RADIUS_MM`; hence
      `DEGENERATE_ARC_RADIUS_MM = SATISFIED_TOL_MM`, re-measured after the
      fix. Census: annihilated arcs 27 -> 0, conflicting 287 -> 314,
      overconstrained 282 -> 257, solvable 1328 -> 1326, violated still 0.
      Three mutants, all restored. Gates: `just lint` exit 0, `uv run
      pyright` clean, geometry suite green. Filed as follow-ups: ARC-BRANCH-1,
      ARC-EXTRUDE-EPS-1.
      [src: SOLVE-CRASH-1 agent report, kernel-architect, 2026-08-29, filed
      by backlog-groomer pass 19]

- [x] (P2, S) **ARC-BRANCH-1 — CLOSED (kernel-architect, 2026-09-04). A
      collapse the constraints do not FORCE is a bad starting guess, not a
      verdict, so the solver re-asks from a different one exactly once.**
      Trial 1906 now ships `r1 = 14.618, r2 = 29.236` at a worst residual of
      3.6e-15 mm — the author's own `e1` untouched, and the branch
      ARC-DEGENERATE-1's live limit named; that test is DELETED here, as its
      docstring required. **The SETTLE-2 tension is real and resolves cleanly:**
      SETTLE-2 governs the settle's relationship to the plain solve it is
      HANDED, and the guard still runs unchanged over whatever baseline it gets;
      the restart runs one layer up and only where the plain solve produced NO
      shippable answer (geometry `read_back` substitutes and the payload gate
      refuses), so the choice is between an answer and no answer, never between
      two answers. **The start pose is the author's own sketch with only the
      collapsed entity relocated**, and the obvious alternative — restart from
      the whole solved answer — was built first and is worse: it inherits the
      first solve's unforced drag on `e1` and reverses the baseline SETTLE-2
      judges against, so the settle's correct answer is discarded and it ships
      `r1 = 10.029`. General finding: **SETTLE-2's guard rests on the premise
      that the plain solve is a walk from the author's own values, and a restart
      seeded from a solved answer is the one thing that breaks it.** Not
      arc-only, and the generality found a second defect: of the **38** corpus
      solves that annihilate an entity, **36 are forced** and 2 are not —
      trial 1906 and trial **1593**, a CIRCLE in the same construction that
      SOLVE-CRASH-1 had counted as forced. Census: solvable 1326 -> **1328**,
      conflicting 314 -> **312**, underconstrained 1295 -> 1297; violated 0,
      reversed 0, annihilated 0/0, raised 0, and no other trial's payload moved
      by a bit. Determinism: two sweeps in one process, identical census and
      2000 payloads bitwise identical. Mutants: disabling the restart reddens 3
      of 5 new tests and restores the pre-fix census; the rejected pose reddens
      2. Gates: `just lint` exit 0, `uv run pyright` clean, geometry suite
      green.
      [src: ARC-DEGENERATE-1, kernel-architect, 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`,
      `services/geometry/tests/test_sketch_degenerate_arc.py`. agentType:
      kernel-architect.

- [ ] (P3, XS) **ARC-EXTRUDE-EPS-1 — the kernel's degenerate-arc guard is a
      `<= 0.0` test where the values that reach it straddle zero.** kind:
      defect (tolerance). Found by ARC-DEGENERATE-1 (2026-08-29):
      `kernel/extrude.py` refuses an arc with `radius <= 0.0`, but the
      annihilated arcs measured in PBT-1's corpus include values of `1.6e-14`
      and `3.9e-14` mm, which clear that guard and become OCCT edges five
      orders under the 1e-7 m kernel tolerance. Exactly the seam
      SOLVE-CRASH-1 documented, one layer down. NOT fixed with
      ARC-DEGENERATE-1 for a reason worth keeping: `geometry.kernel` has NO
      dependency on `geometry.sketch` today, so importing
      `DEGENERATE_ARC_RADIUS_MM` there is a layering change, and writing
      `1e-9`/`1e-7` down a third time is the DRY violation the constant
      already documents itself against. P3 rather than P2 because
      ARC-DEGENERATE-1 closed both ends of the SOLVER, so nothing in the
      service can currently hand `extrude` such an arc — this is
      belt-and-braces against a future producer. ACCEPTANCE: decide where a
      shared degenerate-curve tolerance lives (a neutral module both packages
      may import, or an explicit reviewed kernel->sketch dependency), apply it
      in `extrude.py` and `revolve.py` (which has NO guard at all — a
      zero-radius arc contributes `_ARC_SAMPLES+1` identical samples at the
      centre and silently mis-reports the revolve extent), with a test at the
      measured magnitudes rather than at zero.
      [src: ARC-DEGENERATE-1, kernel-architect, 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/kernel/extrude.py`,
      `revolve.py`, plus wherever the shared constant lands. agentType:
      kernel-architect.

**DOCTICK-GATE (`bd09f5b`, docstring fix `53e62b0`) and SPEC-9 (`e8702d5`)
are both SHIPPED — see Done archive for evidence/gates.**

**RECT-1, SNAP-2, SNAP-3 and MIRROR-1 are all SHIPPED — see Done archive
for full evidence/gates.** Their two live follow-ups stay in Ready:

- [ ] (P2, S) **SNAP-4 — an explicit Fix on a point the draw already grounded
      reads as OVER-CONSTRAINED, and the user did not ask for either half.**
      kind: defect (interaction between two features that are each correct).
      Found 2026-08-16 while integrating SNAP-3, by a test that stopped
      passing for an informative reason rather than by inspection. Draw a line
      starting ON the origin: SNAP-3 correctly authors a coincident from the
      endpoint to the origin. Now press `x` (Fix) on that same endpoint —
      also correct in isolation — and the two constraints pin the same point
      twice, so the sketch reports OVER-CONSTRAINED. MEASURED: the
      `constraints.spec.ts` conflict-recovery case, which removes a bad
      dimension and expects `DOF 0 · CONVERGED`, instead reached
      `OVER-CONSTRAINED` and could not recover; it now draws clear of the
      origin to keep its own subject, which is a workaround in a test and not
      a fix in the product. WHY IT MATTERS beyond the tidiness: the report is
      TRUE — the point genuinely is over-determined — so the diagnosis is not
      lying, but the user authored only one of the two constraints and the
      other arrived silently from a snap. That is the "asks the user to delete
      something they did not knowingly create" shape that SKETCH-2's follow-up
      was filed for. OPTIONS, in preference order: (a) Fix on a point that
      already carries a coincident to the frame REPLACES it (the explicit verb
      supersedes the inferred one) and says so; (b) Fix is refused as "already
      grounded", matching the "Already horizontal." precedent RECT-1 relies on;
      (c) leave it and rely on the redundancy diagnosis — cheapest, and the
      one to argue against. ACCEPTANCE: draw a line from the origin, press `x`
      on that endpoint, and the sketch does NOT report over-constrained; a
      GENUINE over-constraint on the same sketch still does (negative
      control); `constraints.spec.ts`'s conflict case can be moved back onto
      the origin and still recover to `DOF 0 · CONVERGED`.
      [src: SNAP-3 integration, 2026-08-16]
      TERRITORY: `apps/web/src/sketch/constraints.ts` (`applyConstraintAction`,
      the `fixed` branch), `apps/web/src/sketch/store.ts`. agentType:
      frontend-builder.

- [ ] (P2, S) **RECT-2 — should DRAWING alone persist a sketch?** kind: question
      (product decision, not a defect). Raised by RECT-1, which made it live:
      `PartPage.tsx`'s persist gate asks "has this sketch any constraints yet",
      and a drawn rectangle now answers yes immediately. RECT-1 deliberately
      preserved today's behaviour (bind only on a USER-authored constraint) so
      that a constraint fix did not silently change the save model, but the
      question is now worth answering on purpose. FOR auto-binding: Fusion and
      Onshape both autosave, and losing a drawn profile to a stray Escape is a
      real papercut. AGAINST: it creates a sketch feature for every exploratory
      rectangle, and it removes the "Discard N unsaved entities" confirm that
      the FB-13 flow work put there. Whichever way it goes it must apply to
      LINES and CIRCLES too — the inconsistency is the only outcome that is
      definitely wrong. ACCEPTANCE: a decision recorded in docs/VISION.md or
      ROADMAP with its reasoning, and `userConstrained` either removed or
      documented as deliberate. [src: RECT-1 implementation, 2026-08-16]
      TERRITORY: `apps/web/src/routes/PartPage.tsx`,
      `apps/web/src/sketch/store.ts`. agentType: frontend-builder.

**FB-21/FB-9 SHIPPED — see Done archive.**

**EXPORT-1, REGISTER-1, REGISTER-2, VIEWCUBE-1, DXF-2a, DXF-2b, DXF-3,
EXPORT-2, VISION-FIX-1 are all SHIPPED — see Done archive** (`3a7c4ca`,
`044f1f7`, `e024daa`, `c28fbbc`, `a915bf1`, `5bfb528`, `fe72e4d`, `1880db2`,
vision-steward `6dfb597`). Fresh Ready items from the same 2026-08-21
rotational-part audit that produced SOLVE-1/PICK-2 above:

**EXPORT-3 is CLOSED (2026-08-28, frontend-builder) — one failed downstream
feature no longer takes the good body's export with it. The gate was entirely
client-side (the gateway already served the healthy prefix, byte-identical);
`exportGate` now separates CAUSE from PARTIAL and the truth rides three
surfaces (cell, notice, `-partial` filename). Mutation-tested both directions.
See Done archive.**

**REVOLVE-1 is fully SHIPPED (`1b28dd5`, groom pass 15) — closes the last
ABSENT-tier literal in the gateway contract. See Done archive for
evidence/gates.**

- [x] (P1, S) **PICKMARK-OCCLUDE-1 — CLOSED 2026-08-28. A pick diamond now
      sits at a point of its edge the BAND answers with, or it is not drawn
      there.** The agreement census rose 8/21 -> 11/21, and every mark that is
      DRAWN agrees (11/11); the ten that answer nowhere are `buried` —
      `opacity-0`, `pointer-events:none`, still tab-reachable and named, focus
      restores them. Perf measured, not asserted: 0.259-0.270 ms per
      band+surface hit-test, so the recompute is capped at 24 tests/frame
      (~6.5 ms) with a rotating cursor; a 40-step orbit costs +17% blocking
      over the same orbit with no marks. Three wrong turns and the evidence:
      ROADMAP + Done archive. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-8]

- [x] (P1, S) **SEL-8 — CLOSED 2026-08-28. Armed edge picks (Fillet's
      `PICK EDGES` mode) had no hover highlight on the real edge.** The
      ticket's three candidate causes were all wrong; the hit-test was fine
      and the DRAW was discarded by the depth test. Evidence, the mutation
      run and the design argument for keeping the marks: Done archive.
      The mid-face-marks half is NOT closed — see PICKMARK-OCCLUDE-1 above.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-8]

**A11Y-TOOLBTN-1 is CLOSED (2026-08-28, frontend-builder) — `ToolButton` now
wires `aria-describedby` to its caption in EVERY state, not only while
disabled, so an enabled-but-qualified control (e.g. a partial export) reaches
a screen reader instead of announcing nothing. Blast radius measured across
44 call sites via Chrome's own accessibility tree; `ExportToolGroup`'s
name-folding workaround unwound in the same commit. See Done archive.**

**REACH-2-IMPORT-1 is CLOSED (2026-08-28, frontend-builder) — the STEP-import
empty-state slot now sits adjacent to the copy that names it (422px -> 51px
gap at 1280, no growth with screen size) and a new `ProgressTrack` primitive
gives long imports a real indeterminate progress bar + Cancel. See Done
archive.**

**FORCE-CLICK-AUDIT-1 is CLOSED (`6911352`, groom pass 16) — 22 call sites
audited: 18 cargo removed, 3 legitimate refusals proven via a new
`clickRefusedControl` helper, 1 vacuous test fixed. `force: true` now
appears exactly once in `apps/web/e2e/`. See Done archive.**

**PGTEST-GATE is CLOSED (`ef5d1c5`, 2026-08-28, platform-builder) — a missing
PostgreSQL now fails loudly instead of silently skipping 37% of the documents
suite. Pass-8's self-correction to Pass-7 M4 (CI's ubuntu-latest image already
shipped PG 16.15 at the searched path, so the 172 tests were almost certainly
already running) is CONFIRMED from source (`actions/runner-images` fetched
directly), not inherited — see `docs/AUDIT-ENGINEERING.md` M4/N8 and the
correction note there, still accurate, no further action needed. Negative
control exit 0 -> 1; whole-repo suite unaffected (4090 passed). See Done
archive. PGTEST-GATE-VACUOUS-NONGOAL (P3, below) records one deliberately
unfloored case.**

- [x] (P1, XS) **GATE-FLOOR — DONE 2026-08-29 (platform-builder). The two
      named gates were vacuous exactly as audited the fourth time, and
      checking the other three found TWO MORE holes.** Fixed: the named pair
      now carry `EXPECTED_CHECKS` (8 and 23). NEW, and the reason the
      "check the others" instruction earned its keep — (a)
      `check-build-context.py`'s **main** path (the one CI runs, standing in
      for the `docker build` the 403-blocked registry makes unreachable here)
      printed "0 COPY source(s) reach the build context" and exited **0** when
      a Dockerfile parsed but yielded no COPY; now floored at
      `MIN_COPY_SOURCES = 8` against a real 15, plus two self-test cases. The
      audit table's "n/a (straight-line, not list-driven)" was true of its
      SELF-TEST and blind to its main path — it matched the `all([])` idiom
      instead of asking the question the idiom stands for. (b)
      `check-tailwind-scale.py` was never in the table; same `failed = 0`
      shape, exiting 1 only because `max()` raises on an empty sequence — an
      accidental floor one `default=0` from a silent pass. EVIDENCE: identical
      probe, committed HEAD vs fix — HEAD "self-test passed" / "passed - 0
      cases" exit 0; fix "SELF-TEST RAN 0 of 8 / 0 of 23 checks" exit 1;
      `check-build-context` zero-COPY case 0 -> 1; sweep of all seven
      self-test gates with the list emptied at the START of the verdict block
      = 7/7 exit 1 (was 2 vacuous + 1 `ValueError`). Real inputs unchanged and
      green; `just lint` exit 0. Sound on inspection, no change needed:
      `check-doc-tick`, `stage-doc-hunks`, `e2e-shard-audit`,
      `e2e-shard-plan`, `check-licences`, `check-compose`.
      `check-ui-parity.py` has the same main-path vacuity but gates nothing
      (in neither `just lint` nor CI) — filed as GATE-FLOOR-2 below.
      Original entry follows.
      kind: defect. MEASURED
      (`docs/AUDIT-ENGINEERING.md` "Pass 7" M7, reproduced not inferred):
      `check-workflow-concurrency.py:481` and `check-mutation-markers.py:
      1115` both use `if all(ok for ok, _ in results)` with no count floor;
      injecting an empty check list into each makes `--self-test` print
      "self-test passed — the gate can fail" / exit 0. `e2e-shard-audit.py:
      309` and `stage-doc-hunks.py:544` already carry the fix (an
      `EXPECTED_CHECKS` constant + `if len(results) < EXPECTED_CHECKS:
      return 1`). FIX: copy that four-line pattern into the two gates named
      above. ACCEPTANCE: the same empty-list injection that currently prints
      "the gate can fail" now correctly fails; `just lint` stays green on
      the real gates.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M7, filed by backlog-groomer
      pass 8]
      **Bumped P2→P1: reproduced UNCHANGED a second time**
      (`docs/AUDIT-ENGINEERING.md` "Pass 8" N3): `check-mutation-markers.py`'s
      own self-test message literally prints `"self-test passed - 0 cases"`
      and returns 0 — it has `len(results)` in hand, interpolates it into
      the success string, and never compares it to anything. Two
      consecutive passes recommending an already-written four-line fix
      with zero action is a process signal on its own, independent of the
      gate's own severity.
      **REPRODUCED UNCHANGED A THIRD TIME, groom pass 11 (2026-08-24,
      engineering Pass 9 N8a):** re-ran with `tail`-swallowed exit-code
      measurement corrected (a methodological note worth keeping: piping
      `--self-test` through `tail` reports `tail`'s exit code, not the
      gate's, and would print 0 for a gate that correctly exited 1) — both
      gates still print their own vacuity and exit 0. Three passes, zero
      action, four-line fix each: this is now the board's clearest example
      of the "gate hygiene items don't get built" pattern the same audit
      names in N10.
      TERRITORY: `scripts/check-workflow-concurrency.py`,
      `scripts/check-mutation-markers.py`. agentType: platform-builder.

- [ ] (P3, XS) **GATE-FLOOR-2 — the two vacuity gaps GATE-FLOOR found that
      gate nothing today, so neither is urgent, but both become live the
      moment somebody wires them in.** kind: defect, filed by platform-builder
      2026-08-29 from the GATE-FLOOR sweep. (a) `check-ui-parity.py` has the
      same main-path hole `check-build-context` had: `rows = classify(...)` then
      `gaps = [... != AUTHORABLE]`, so a spec that fails to load or an empty
      corpus yields no rows, no gaps, no orphans and exit 0 — and its numbers
      are quoted in `docs/ROADMAP.md`'s Current focus (84/85 operations,
      97/109 literals), i.e. already trusted as a measurement while being
      unfloored. It is in neither `just lint` nor CI, which is the only reason
      this is P3. (b) `check-compose.py` has no `--self-test` at all; it is
      honest today only because direct `base["documents"]` indexing raises on
      a missing service, which is a property of how it happens to be written
      rather than a guarantee anybody checked. FIX: a count floor on
      `check-ui-parity`'s literal/operation walk, and a `--self-test` for
      `check-compose` carrying a negative control that reproduces a real
      compose defect. TERRITORY: `scripts/check-ui-parity.py`,
      `scripts/check-compose.py`. agentType: platform-builder.

- [ ] (P2, S) **DEP-AUDIT — no dependency-vulnerability gate exists anywhere
      in the repo; a 60-second local `pnpm audit` finds 18 advisories (13
      high).** kind: capability. MEASURED (`docs/AUDIT-ENGINEERING.md`
      "Pass 7" M8): no `.github/dependabot.yml`, no `pnpm audit`/`pip-audit`
      step in CI, no CodeQL, no container scan — the licence gate
      (`check-licences.py`) answers a different question entirely (what a
      dependency is licensed as, not whether it's vulnerable). All 18
      current findings are in `devDependencies` (eslint/openapi-typescript/
      postcss/jsdom chains), none reach the shipped SPA bundle or a service
      image today — P2, not P1, because of that path check, but two
      (`js-yaml` inside `just gen`, `postcss`/`nanoid` at build time) are a
      supply-chain path even so. FIX: `.github/dependabot.yml` (npm + pip +
      github-actions ecosystems, weekly); a non-blocking `pnpm audit
      --audit-level=high` step in `ci.yml`; `pip-audit` against `uv.lock`
      for the Python half (no `uv audit` subcommand exists). ACCEPTANCE:
      dependabot.yml present and valid; CI runs both audit commands and
      surfaces (not blocks) results.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M8, filed by backlog-groomer
      pass 8]
      **ADDENDUM this pass** (`docs/AUDIT-ENGINEERING.md` "Pass 8" N4,
      first-ever Python-side scan): `pip-audit` found **1** advisory,
      `cryptography 49.0.0` (PYSEC-2026-3552, a Bleichenbacher oracle in
      `pkcs7_decrypt_*`) — traced to `moto`'s `joserfc` dependency in the
      root `dev` group; `grep -rn pkcs7` across `services`/`packages` is
      empty (not called), and `uv sync --frozen --no-dev` means it's
      **absent from every shipped image**. Add `pip-audit` to the FIX list
      alongside `pnpm audit`; also add a test asserting `--no-dev` in the
      image build, since the Python answer is currently good only because
      of an untested Dockerfile flag, not because of anything enforced.
      **STILL UNBUILT, groom pass 11 (2026-08-24, engineering Pass 9 N10):**
      `.github/dependabot.yml` still absent, no `pnpm audit`/`pip-audit`
      step in any workflow.
      TERRITORY: `.github/dependabot.yml` (new), `.github/workflows/ci.yml`.
      agentType: platform-builder.

- [ ] (P2, XS) **SPEC-8 — `materials.spec.ts` silently stops asserting a
      mass-properties claim when its subject disappears.** kind: defect
      (test, on a geometric-correctness claim). MEASURED
      (`docs/AUDIT-ENGINEERING.md` "Pass 8" N5, uncommitted, recovered and
      preserved by backlog-groomer pass 9): `:267`
      `if ((await picker.count()) === 0) return;` skips the rest of the
      test — including the mixed-material combined-mass assertion
      (`84.56`) — if `material-default-select` isn't found. The comment's
      premise expired: `MaterialSection.tsx:124` ships that testid today,
      so the guard is now pure risk (a future regression removing/renaming
      the picker reports PASS instead of catching it). Same shape at
      `:249`. FIX: `await expect(picker).toHaveCount(1)` in place of the
      early return at both sites. ACCEPTANCE: temporarily rename the
      testid and confirm the test now FAILS instead of passing; revert and
      confirm green.
      [src: docs/AUDIT-ENGINEERING.md "Pass 8" N5, filed by backlog-groomer
      pass 9]
      **STILL UNFIXED, groom pass 11 (2026-08-24, engineering Pass 9 N8d):**
      both early returns unchanged at `:249`/`:267`; re-swept all 126 spec
      files and confirmed the other four early-return sites are TypeScript
      narrowing after an explicit `not.toBeNull()`, not the same escape —
      the exposure is exactly these two lines.
      TERRITORY: `apps/web/e2e/materials.spec.ts`. agentType:
      frontend-builder.

- [ ] (P2, XS) **AUDITOR-PORTS-1 — the two auditors are told not to
      coordinate, but both default to the SHARED ports (8000-8002, 5173),
      so two audits scheduled close together cost the later one a lost
      hour rebuilding an isolated stack just to get a finding.** kind:
      capability (process). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 8"
      recommendation #8): the engineering audit found the product
      auditor's stack live on the shared ports mid-pass and had to boot an
      isolated stack (the documented CLAUDE.md recipe, ~1 hour) to run any
      browser suite at all — second consecutive pass this has cost real
      time. FIX: the product-auditor agent brief defaults to an isolated
      port profile (it runs the longer, heavier browser session), leaving
      the shared ports free for the lighter/quicker engineering-audit
      checks. ACCEPTANCE: `.claude/agents/product-auditor.md` states an
      isolated-port default, pointing at CLAUDE.md's existing recipe;
      next time both audits land in the same window, neither blocks the
      other.
      [src: docs/AUDIT-ENGINEERING.md "Pass 8" recommendation #8, filed by
      backlog-groomer pass 9]
      TERRITORY: `.claude/agents/product-auditor.md`. agentType:
      platform-builder.

**QA-R1 is CLOSED (`5957252`, groom pass 15) — fixed the primitive
(`Flyout` label collapse), not the instance. See Done archive.**

**QA-R2 is CLOSED (`0cee656`, e2e barrier hardened `d2b1d26`, groom pass
15) — the angle glyph now reads `SolvedSketch.angles`. See Done archive.**

**REACH-3-FLOW is CLOSED (2026-08-28, frontend-builder) — Sheet 1 is now born
from the orientation proposal (a 40x40x150 column lands A4 portrait at 1:2,
was landscape at 1:5), via one `sheetHeaderForNewSheet()` derivation shared by
all four create paths. The orientation-flip half's promised re-fit was
IMPOSSIBLE server-side (documents refuses a per-view re-scale, H2), so the
trade moved to the set-up screen instead of shipping a broken promise. See
Done archive. Residual: **SHEET-RESCALE-1** below.**

- [ ] (P2, S) **SHEET-RESCALE-1 — a laid-out sheet's scale cannot be
      changed by anything, so the only way to re-scale a drawing is to start
      another one.** kind: capability gap (not a regression — no client ever
      could). MEASURED 2026-08-28 while closing REACH-3-FLOW, against the real
      stack: `PATCH /views/{id}` with a new `scale` returns 422
      `sheet_view_scale_mismatch` on any multi-view sheet (documents' H2 "one
      sheet, one source, one scale" guard), and the refusal cannot be
      sequenced around — the guard compares against `siblings[0]`, which still
      holds the OLD scale whichever view you write first. There is no
      sheet-level re-scale verb, and post-layout the web Scale control is a
      read-only `Readout`, so the scale a sheet was laid out at is permanent.
      Consequences the user feels: flipping paper orientation cannot re-fit
      (REACH-3-FLOW closed this by making the cell honest instead), and a part
      that grows after drafting can only be re-scaled by deleting the sheet.
      FIX: a sheet-level re-scale on `PATCH /sheets/{sheet_id}` that rewrites
      every view's scale in ONE transaction (the H2 invariant then holds
      throughout — it is per-view writes that cannot satisfy it), plus the web
      Scale picker staying live post-layout.
      ACCEPTANCE: re-picking Scale on a laid-out four-view sheet re-draws every
      view at the new scale with the title block agreeing; the H2 guard still
      refuses a genuinely divergent PER-VIEW write; an orientation flip can
      then offer the fit its own cell quotes.
      [src: REACH-3-FLOW measurement, filed by frontend-builder 2026-08-28]
      TERRITORY: `services/documents/src/documents/drawings.py`,
      `services/gateway/**`, then `apps/web/src/routes/DrawingPage.tsx`.
      agentType: backend-builder (then frontend-builder).

- [ ] (P2, XS) **TITLEBLOCK-STAMP-1 — the projection-convention symbol
      `5438b73` shipped appears on screen and vanishes from every print.**
      kind: capability (deliberate, documented deviation — not a defect in
      what shipped). `5438b73`'s own commit message: the plan put the
      convention cell in the sheet's TITLE BLOCK (a drafter's actual reading
      location, and the right long-term home) but `ComposedTitleBlock` is
      composed SERVER-side, so a DOM-only cone symbol there would be worse
      than absent — present on screen, gone from every exported SVG/PDF/DXF.
      The cell was placed in the sheet header instead, correctly, as an
      interim step. FIX: stamp the ISO cone symbol (mirrored by
      `right_sx`'s sign, per the header cell's own derivation) into the
      geometry service's composed title block so it reaches every export
      format, not just the screen. ACCEPTANCE: an exported SVG/PDF/DXF of a
      first-angle sheet carries the 1ST-angle cone in its title block;
      third-angle carries the mirrored symbol; the on-screen header cell and
      the exported stamp never disagree (shared derivation, not two).
      [src: `5438b73` commit message's own deviation note, filed by
      backlog-groomer pass 14]
      TERRITORY: `services/geometry/src/geometry/drawings/` (title block
      composition). agentType: kernel-architect.

**ASMDRAW-FIT-1a is CLOSED (`79ca41c`) — `GET /assemblies/{id}/extents`
returns the mate-solved compound's AABB, asserted on the geometry (a fixture
where solved and seeded differ), never the status code. See Done archive.**

**ASMDRAW-FIT-1b is CLOSED (`69b3ef7`) — the assembly drawing sheet fit-scales
off those solved extents (1:1 -> 1:2 on the founder's rig; title-block
overlap gone, all four frames measure 0 px² overlap). See Done archive.**

**EXTRUDE-COARSE-STEP-1 is CLOSED (`1661a5b`) — two independent defects, both
fixed: the coarse step now lands on the next multiple of the step in the
direction pressed (12.4713 -> Shift+Up -> 15, not 15.5/16), and a queued-ack
race that silently dropped fast keyboard presses is gone. See Done archive.
Note: `nudgePlacement` (drawing authoring) still uses the older round-then-add
variant this fix deliberately did not touch — see NUDGE-PLACEMENT-QUANTISE-1
below.**

- [ ] (P3, S) **NUDGE-PLACEMENT-QUANTISE-1 — `nudgePlacement`
      (`apps/web/src/drawing/authoring.ts`) rounds-then-adds, so a coarse
      press from off-grid skips the value the user is standing next to.**
      kind: defect. From 12.4713 a coarse press gives 13, silently skipping
      12.5 — the same shape EXTRUDE-COARSE-STEP-1 (`1661a5b`) fixed on the
      extrude drag handle by taking "the next multiple of the step in the
      direction pressed" instead of round-then-add. That commit deliberately
      did NOT extract a shared helper: the two nudges share three lines of
      arithmetic and nothing else (`nudgePlacement` moves a 2-D seat on a
      sketch-authoring state machine in sheet mm; `nudgeDepth` moves a 1-D
      depth clamped to a submittable range with its own key map), so a
      shared primitive would move code out of both files without removing
      any duplicated LOGIC — the premature abstraction DRY excludes. What
      they must share is the RULE, and `1661a5b` states it in both files and
      points each at the other; this item brings `nudgePlacement`'s
      BEHAVIOUR into line with the rule it already cites, without merging
      the two functions. FIX: change `nudgePlacement`'s quantisation from
      `round(v/step)*step` (or equivalent round-then-add) to the next
      multiple of the step in the direction of the press, matching
      `steppedDepth`'s rule. ACCEPTANCE: from 12.4713, a coarse press lands
      on 12.5 (not 13); a unit test reproduces the round-then-add failure
      (asserts 13 today) and reddens against the fixed function; a case
      confirms the direction-of-press semantics (e.g. a downward coarse
      press from 11 lands on 10, not 5, mirroring `steppedDepth`'s own
      negative-direction case).
      [src: `1661a5b` commit's own deliberately-foreign-territory note,
      filed by backlog-groomer pass 17]
      TERRITORY: `apps/web/src/drawing/authoring.ts` (`nudgePlacement`),
      its unit test file. agentType: frontend-builder.

- [ ] (P3, S) **CHECKUIPARITY-FP-1 — `scripts/check-ui-parity.py`
      misclassifies the hem-type literals in both directions: `"open"` reads
      AUTHORABLE while `"closed"` — the value the UI actually authors —
      reads RENDER-ONLY.** kind: defect (tooling — the scan's own docstring
      already admits residual error in both directions; this is a concrete
      instance, and it lands in the direction that matters, since it hides a
      literal that IS reachable and blesses one that is not). Cause:
      `_reachable_in`'s bare-substring match — the string `"open"` appears
      inside unrelated identifiers in the web corpus (e.g. words containing
      "open" as a substring), producing a false AUTHORABLE hit for a literal
      the UI may not actually author, while the exact match for `"closed"`
      the hem form actually sends is not found by the same loose logic.
      FIX: match hem-type literals as whole tokens/string values (e.g. a
      quoted-string or property-value boundary), not bare substrings.
      ACCEPTANCE: re-running the scan against the current web corpus
      classifies `hem_type: "open"` and `hem_type: "closed"` correctly
      (closed reads authorable, since `HemEditor`/equivalent sends it; open
      reads per its actual reachability, not a substring accident); a
      self-test fixture reproduces today's false positive (a corpus file
      containing "open" only inside an unrelated identifier, and "closed" as
      an actual authored literal) and fails against the unfixed matcher.
      [src: found during groom pass 17 while reconciling HEM-1's closure
      against `check-ui-parity.py`'s own reachability claims]
      TERRITORY: `scripts/check-ui-parity.py`. agentType: platform-builder.

## Next (P2)

**Filed groom pass 27 (2026-09-23) — sketch-Fit follow-ups + a DRY/infra pair:**

- [ ] (P2, S) **E2E-SHARD-COUNT-1 — e2e shards run ~31.3 CI-min each against
      the 40-min step cap (1.3x headroom), and the workflow's own header
      already says to weigh N=5/6.** kind: capability (CI infra). `7c9ff95`
      (groom pass 27) fixed the shard-4 timeout by re-measuring the
      duration manifest, but the resulting spread's headroom is 1.3x — down
      from a documented 2.1x a month ago, as the suite grew 145→180 spec
      files — and `.github/workflows/e2e.yml`'s own header states "by the
      rule above that is the point to weigh N=5 or 6" once T/N approaches
      the cap. ACCEPTANCE: raise the shard matrix to 5 or 6 (per the
      workflow's stated rule: N=6 puts T/N near 12.6 min per the
      documented arithmetic), re-run `e2e-shard-plan.py --self-test` and a
      real CI run to confirm the new spread and headroom, and state both
      numbers in the workflow header (the file already tracks this history
      inline — extend it, don't replace it). Related but distinct from
      SHARD-MANIFEST-CI-1 (that ticket is about the manifest's SOURCE —
      local vs CI-measured costs — not the shard COUNT). [src: `7c9ff95`
      header note, filed by backlog-groomer pass 27] TERRITORY:
      `.github/workflows/e2e.yml`, `scripts/e2e-shard-plan.py`. agentType:
      platform-builder.
- [ ] (P2, S) **VIEWBAR-DRY-1 — the sketch Fit bar duplicates the part view
      bar's instrument-shell styling in `Viewport.tsx` instead of sharing
      `components/ViewBar.tsx`.** kind: defect (DRY, frontend). `f9fcce6`'s
      `SketchViewBar` (in `Viewport.tsx`) and `ViewBar`'s own container
      (`components/ViewBar.tsx`) both render `role="toolbar"`,
      `data-viewport-chrome="view-bar"`, and the identical shell classes
      (`flex items-stretch border border-hairline bg-anvil shadow-float`)
      — the exact "fix the primitive, never the instance" case CLAUDE.md's
      design mandate names. **RE-VERIFIED after `5444fa8` moved the
      sketch bar to hang off the reference cube:** the duplication survives
      the move — only the POSITIONING classes now differ
      (`SketchViewBar` anchors to the cube's own seat box via
      `right-full top-1/2 mr-2 -translate-y-1/2`, `ViewBar` docks at
      `bottom-3 left-1/2 -translate-x-1/2`), the shell styling is still
      copy-pasted. ACCEPTANCE: extract the shared SHELL (role, chrome
      attribute, border/background/shadow/flex classes) into one primitive
      both compose, leaving only each bar's own positioning classes at the
      call site; zero visual change (screenshot diff at 1280x800 and a
      small-laptop width); a change to the rail's chrome (border, shadow)
      now requires editing one place. [src: found while reviewing
      `f9fcce6`, re-verified against `5444fa8`, filed by backlog-groomer
      pass 27] TERRITORY: `apps/web/src/components/
      ViewBar.tsx`, `apps/web/src/viewport/Viewport.tsx`. agentType:
      frontend-builder.
- [ ] (P2, S) **SKETCH-FIT-GRID-OCCLUDE-1 — a reported dark region near the
      top-left of the sketcher may be hiding grid content; needs
      re-measurement before a fix.** kind: defect (frontend, UNVERIFIED
      dimensions). Reported at ~608x65px at the top-left of the sketcher
      canvas; see `docs/screenshots/sketch-fit-after-1280.png`. A pixel
      scan of that specific PNG did not find a flat/uniform block of those
      exact dimensions at that position (the feature-tree panel there
      measures ~332x236 and IS a legitimate DOM panel, not a canvas
      artifact) — so either the dimensions/position have drifted, the
      report was against a different viewport state, or this is a rendering
      difference not visible in a static screenshot diff. ACCEPTANCE: a
      frontend-qa or builder pass reproduces this LIVE against the running
      app first (not from the static PNG) before scoping a fix; if it does
      not reproduce, close with the measurement that shows so, the same
      discipline LAYOUT-1 used. **RE-CHECKED against the screenshot
      `5444fa8` refreshed** (same pass, moved the Fit bar off the
      bottom-centre seat) — still no flat block of those dimensions found;
      the referenced image is now stale a second time over, so measure
      against the RUNNING app, not any static PNG in this repo. [src:
      reported, unverified by backlog-groomer pass 27] TERRITORY: `apps/web/src/viewport/
      SketchScene.tsx` (grid render), `apps/web/src/routes/PartPage.tsx`
      (feature tree panel). agentType: frontend-qa (reproduce) then
      frontend-builder (fix).

**SOLVE-CRASH-1 is CLOSED (2026-08-29, kernel-architect, arbitrated P2->P1) —
the untyped 500 is gone. The twelve crashes were TWO defects wanting opposite
answers, measured before a fix was chosen: 3 had a negative radius of real
magnitude (a planegcs branch convention, not degeneracy) and now solve
normally at 1.8e-13 mm worst residual; the other 9 are genuinely annihilated
(`r=0` the unique solution) and now return `sketch_conflicting` via the
existing payload gate rather than crashing. No new machinery, no contract
change. Census: raised 12 -> 0, solvable 1327 -> 1328, conflicting 276 -> 287.
See Done archive / `docs/CHANGELOG.md` for the full two-defects-one-crash argument.**

**Filed groom pass 25 (2026-09-15) — gauntlet + code-review + DIRECTION-ASSEMBLIES.md findings, ranked by scorecard/correctness impact:**

- [ ] (P2, M) **PERF-REAL-3 — a real part's mesh payload is 142MB, gzip only
      reaches 1.58x.** kind: defect (perf, delivery). MEASURED on
      `rc-buggy-suspension` (211 solids, 6 867 576 triangles): 142MB GLB,
      90MB gzipped. `docs/PERF.md`'s 5.2x-11.8x compression figures were
      measured on toy parts, where the win was JSON overhead; a real mesh is
      dominated by incompressible vertex data, and 142MB is not deliverable
      to a browser on any connection a user has. Ranked #3 in
      `docs/GEOMETRY-QA.md`'s gauntlet ranking. ACCEPTANCE: mesh
      quantization (e.g. Draco or a fixed-point vertex encoding) measurably
      shrinks the same fixture's payload, stated as a before/after number;
      per-face-primitive glTF export (one primitive per B-rep face) is a
      named contributor worth checking as a separate lever. [src: geometry-qa
      gauntlet, `docs/GEOMETRY-QA.md` 2026-09-15] TERRITORY:
      `services/geometry/src/geometry/kernel/tessellate.py` (or wherever GLB
      is assembled). agentType: kernel-architect.

- [ ] (P2, S) **NURBS-FIXTURE-1 — acquire a licence-clean foreign NURBS part
      (>1000 faces) to regression-test mesh determinism; this is an
      acquisition problem, not an engineering one.** kind: question
      (blocked on acquisition). The `mesh_glb_id` non-determinism F2 fixed
      this pass reproduced ONLY on foreign imports at 1018+/4123 faces
      (gearbox-11752, kuka-kr600); twelve of our OWN goldens exported to
      STEP and re-imported are all byte-idempotent (0 differing bytes), so
      the fix has no regression fixture that can catch a re-introduction of
      the bug. `just gauntlet`'s five fixtures are fetched by URL+sha256 and
      explicitly NOT redistributable (no LICENSE in the hosting repo).
      ACCEPTANCE: find or commission a NURBS-heavy STEP part >=1000 faces
      under a licence this MIT project CAN commit (public-domain, CC0, or
      author permission), add it as a committed golden, and confirm it
      reproduces the pre-fix non-determinism when the fix is reverted. [src:
      geometry-qa gauntlet, `docs/GEOMETRY-QA.md` 2026-09-15, F2 follow-up]
      TERRITORY: `services/geometry/goldens/**`. agentType: geometry-qa /
      founder (licensing/acquisition decision).

- [ ] (P2, S) **STEP-ROUNDTRIP-COVERAGE-1 — the golden suite has no fixture
      at assembly scale, and a real one shows drift the corpus cannot see.**
      kind: defect (golden coverage gap). MEASURED: `rc-buggy-suspension`
      (211 solids, 26 306 edges) round-trips through STEP export/re-import
      gaining 22 edges, with faces/solids/shells all identical; the KUKA's
      converged round-trip volume delta is 5.3e-6, stable across
      tolerances — 53x the golden suite's `ROUNDTRIP_TOL=1e-7`. No existing
      golden has 10 000+ edges or 200+ solids, so this scale is structurally
      unreachable by the corpus today. ACCEPTANCE: root-cause the +22 edges
      (a specific OCCT re-tessellation/seam-splitting behaviour, named) and
      either fix it or add a golden at comparable scale with a documented,
      deliberately looser tolerance for large assemblies — do not silently
      loosen the existing 1e-7 bound for small parts. [src: geometry-qa
      gauntlet, `docs/GEOMETRY-QA.md` 2026-09-15, Finding 4] TERRITORY:
      `services/geometry/src/geometry/kernel/export.py`,
      `services/geometry/tests/goldens/**`. agentType: kernel-architect.

- [ ] (P2, S) **GAUGE-QUIESCE-1 — `pattern-gauges.spec.ts`'s 1200ms quiesce
      window is under-margined on both trees.** kind: defect (test
      hardening, not a product defect). MEASURED by the CRAFT-13 fix
      (`b4e7821`): the post-release settle tail the window races is
      1.09-1.12s on the base tree and 0.78-0.80s with the fix applied — the
      fix makes it SHORTER, not the window safer, and both readings sit
      close enough to 1200ms that CI contention can plausibly cross it (two
      cases, `:251` contract-β and `:333` arrow keys, already fail in batch
      and pass in isolation on both trees). ACCEPTANCE: raise the window
      with margin against the measured 1.12s tail (state the new value and
      why), or replace the fixed timeout with a condition-based wait on the
      actual settle signal if one exists. [src: CRAFT-13 fix, `b4e7821`,
      2026-09-15] TERRITORY: `apps/web/e2e/pattern-gauges.spec.ts`.
      agentType: qa-tester.

- [ ] (P2, S) **SCOREFRESH-PENDING-1 — `PENDING` on the scorecard freshness
      gate is an unbounded self-granted exemption.** kind: defect (gate
      completeness, self-referential). `scripts/check-scorecard-freshness.py`
      exempts any row whose cell contains the word `PENDING` from its git
      staleness check, with no age bound, expiry, or cap on how many rows
      may be PENDING at once — and the self-test asserts this is intentional
      ("marking most rows PENDING does NOT trip the vacuity floor"). Live
      example the day it shipped: 5 of 13 rows read PENDING, including the
      two rows that day's two biggest commits were evidence for. A row
      marked `PENDING — awaiting the gauntlet` in September could still say
      PENDING in March with September's prose beside it, and the gate would
      report green every day. ACCEPTANCE: record the sha or date a row was
      marked PENDING and report STALE once the row's territory has moved
      more than N commits (or M days) since, without breaking the existing
      non-vacuity self-test. [src: code review P1-5, `docs/CODE-REVIEW.md`,
      `451245c`] TERRITORY: `scripts/check-scorecard-freshness.py`.
      agentType: platform-builder.

- [ ] (P2, S) **REQUIRED-QUERY-1 — `Operation.required_query` is generated
      for all 86 scripting-API operations and enforced by nothing.** kind:
      defect (structural, gate gap — SCRIPT-1 follow-up, related to the
      `delete_feature` P0 this pass fixed one instance of). Ten operations
      declare a required query param (`expected_version`,
      `expected_tree_version`, `kind`, `format`); until `_send` enforces it,
      the scripting API's "no undeclared call" guarantee covers bodies and
      paths only, and every future verb added to the library can reproduce
      the same 422-on-every-call defect for free. Related and unenforced in
      the same place: an UNDECLARED query key is silently ignored by
      FastAPI's `extra="ignore"` default. ACCEPTANCE: `_send` validates that
      every operation's declared `required_query` keys are present before
      issuing the request, with a clear client-side error naming the
      missing key(s) rather than a 422 from the server; a regression test
      per operation carrying a required query key. [src: code review P2-6,
      `docs/CODE-REVIEW.md`, `451245c`] TERRITORY:
      `packages/loft-script/src/loft/_operation.py`,
      `scripts/gen-py-operations.py`. agentType: backend-builder.

~~**CSP-1**~~ — **CLOSED (`ed8c3d7`).** `scripts/dist-leg.sh` (`just
      dist-leg`, e2e.yml's `dist-bundle` job) builds the bundle, serves it
      through the real production nginx config, and drives Chromium against
      it — the missing browser-against-the-BUILT-artifact leg this ticket
      asked for, first. Found the proposed `font-src 'self'` CSP was wrong
      (Vite inlines fonts as `data:` URLs, 8 violations, silent fallback-
      typeface render); shipped `font-src 'self' data:`, verified with a
      positive control (an injected inline script both fails to execute and
      is the only violation recorded) plus a second, independently-derived
      violation count from Chromium's own console. TERRITORY:
      `deploy/docker/web/nginx.conf`, `scripts/dist-leg.sh`,
      `scripts/render-web-nginx.py`, `apps/web/e2e-dist/**`.

- [ ] (P2, L — spike first, S) **PERF-ASM-1 — measure assembly performance at
      realistic instance counts before proposing a fix.** kind: capability
      (measurement first). `docs/design/DIRECTION-ASSEMBLIES.md` §7: no
      assembly in this repo has ever been solved/rendered past 2 instances;
      build a fixture (1 unique bracket + 1 unique plate + N identical
      fastener instances, N=10/30/100) and measure, separately: evaluate+
      resolve+solve+tessellate wall clock; time-to-first-frame; orbit/zoom
      frame rate with the assembly loaded; time to author+solve one more
      mate once the scene is populated. Record as a golden + CI budget (same
      shape as existing part-evaluation perf gates, RESEARCH §9). ONLY IF a
      number is bad, propose the smallest fix ranked by likelihood: (1)
      viewport draw-call/material count if render/orbit is the bottleneck
      (`apps/web/src/viewport/**`-only); (2) moving assembly evaluation onto
      the arq queue if solve wall-clock blocks the request thread (a
      RESEARCH §4/§10 update in the same commit as the code). Do NOT build
      either fix speculatively ahead of the number. ACCEPTANCE: a checked-in
      perf golden/budget where none existed; a stated, measured verdict on
      whether N=30/N=100 meet a defined "interactive" bar; any shipped fix
      justified by the specific number it responds to, named in the commit.
      [src: vision-steward, `docs/design/DIRECTION-ASSEMBLIES.md` §7,
      2026-09-15] TERRITORY: `services/documents/src/documents/assemblies.py`,
      `apps/web/src/viewport/AssemblyScene.tsx`. agentType: kernel-architect
      / frontend-builder (split once the number names the bottleneck).

- [ ] (P2, M) **PICK-ASM-1 — prove MATE-1's occlusion fix at real clutter,
      not the golden's clean two-plate case.** kind: verification-first
      (the fix may already be sufficient). Build a 3-4 instance scene where
      at least two DIFFERENT faces on DIFFERENT instances project to
      overlapping screen regions from a default camera angle — the
      realistic case, not the original defect's clean arrangement — and
      confirm the existing `mateDepthStack` cycling reaches every
      plausible face. If it does not, the fix is scoped to
      `apps/web/src/viewport/mateDepthStack.ts` and its consumers, following
      MATE-1's own pattern. ACCEPTANCE:
      `apps/web/e2e/mate-buried-face-cluttered.spec.ts` proves every
      occluded face in a 3+-instance scene is reachable via the existing (or
      extended) depth-cycling mechanism using a real `page.mouse.click` at
      the resolved screen point — not `force: true` (CLAUDE.md's own
      standing rule). [src: vision-steward, `docs/design/
      DIRECTION-ASSEMBLIES.md` §7, 2026-09-15] TERRITORY:
      `apps/web/src/viewport/mateDepthStack.ts`,
      `apps/web/e2e/mate-buried-face-cluttered.spec.ts`. agentType:
      frontend-builder.

- [ ] (P2, M) **BOM-ASM-1 — recursive/indented BOM, one level of nesting.**
      **REPLACES the prior "Assemblies — RECURSIVE / indented BOM" entry**
      (same scope, pulled forward per `docs/design/DIRECTION-ASSEMBLIES.md`
      §7, which closes a real gap in the ➖ Assemblies scorecard row rather
      than deferring behind Phase 5). Walk the (already-acyclic)
      sub-assembly instance graph; roll a part appearing N× inside a
      sub-assembly instanced M× up to N·M; carry a `level`/`parent_key` so
      the client can render an indented tree. The flat aggregation,
      `BomLine` DTO, and acyclicity guarantee already exist — this is an
      additive walk over them, not a new mechanism. ACCEPTANCE: an assembly
      containing a nested sub-assembly reports the CORRECT rolled-up
      quantity for a part instanced inside it (today's flat read undercounts
      this — verify the undercount reproduces before fixing it, then verify
      it's gone); the flat BOM (no nesting) stays byte-identical; contracts
      regenerated (`just gen-verify` — additive field crosses
      documents→gateway→web). [src: vision-steward, `docs/design/
      DIRECTION-ASSEMBLIES.md` §7, 2026-09-15] TERRITORY:
      `services/documents/src/documents/assemblies.py`,
      `packages/contracts`. agentType: backend-builder.

- [ ] (P2, M) **FLOW-ASM-1 — an inferred first mate, not a mate-connector
      redesign.** kind: capability (flow, scope-bounded deliberately). Does
      NOT add a new persisted reference type: when a newly-inserted (or
      newly-selected) instance has exactly one planar face or circular edge
      geometrically compatible (coincident- or concentric-candidate, within
      tolerance) with exactly one face/edge on an already-placed nearby
      instance, surface a one-click "Mate these" suggestion using the
      EXISTING `coincident`/`concentric` mate-create endpoint — no schema
      change, purely a suggestion computed and discarded client-side (or a
      thin geometry-side candidate-pairs query, an implementation choice for
      the builder). If more than one candidate is plausible, show the
      ambiguity as a short pick list — never guess. ACCEPTANCE: inserting a
      second instance next to a first, where exactly one obvious face/edge
      pair matches, offers a one-click mate producing the SAME resolved mate
      a manual pick+pick+submit would; an ambiguous scene (two equally
      plausible pairs) surfaces the choice; e2e proves the click-through
      path end-to-end including the existing snap-solve animation. [src:
      vision-steward, `docs/design/DIRECTION-ASSEMBLIES.md` §7, 2026-09-15]
      TERRITORY: `apps/web/src/assembly/**`. agentType: frontend-builder.

- [x] (P2, S) **CAMRESTORE-1 CLOSED (2026-09-04, frontend-builder) — leaving a
      sketch gives the VIEW back, not just the camera.** The sketcher remembers
      the pose it takes and requests it back through the same view-command seam
      the rail and the reference cube use (a new `restore` kind carrying a
      `ViewPose`), so the part rig performs it — one rig on the camera, an ease,
      `prefers-reduced-motion` honoured. Measured with the direction read off
      the live camera, not a brightness census (that census is exactly what this
      defect broke): pre-fix the exit view was **78.05 deg** off the pre-entry
      view (and read (0,-1,0) — straight down, the ticket's flat diamond),
      **90.00 deg** from a named FRONT, and **78.04 deg** across the ticket's own
      draw-and-save flow; post-fix all three are **<= 1 deg**. A deliberate
      mid-sketch orbit is NOT overruled — the remembered pose is a default an
      explicit action beats, the `905fcc4` rule — and mid-ease gestures do not
      count, because the ease overwrites them. Orthographic zoom is carried, so
      a parallel view returns at the same apparent size (5% band). 2 unit cases,
      4 e2e cases, mutation-tested in both directions: no-restore reddens 3 of 4
      and leaves the orbit case green; unconditional-restore reddens ONLY the
      orbit case (27.25 deg of overruled turn). Screenshots:
      `docs/screenshots/camrestore-sketch-exit-{before,after}-laptop.png`. Two
      specs needed the wait they had been getting by accident stated out loud:
      `part-visibility`'s ghost A/B (its second sketch entry now eases, where a
      stranded camera used to make the park a no-op) and, separately,
      `founder-picking`'s face-seat pick, which was RED at the tip for its own
      reason — see the entry below.

- [ ] (P1, XS) **TIPRED-1 — `qa-sketch-frame.spec.ts` "a FACE-SEATED sketch's
      origin is selectable and grounds a profile to the face centroid" is RED at
      the branch tip.** kind: defect (CI). Found while sweeping for CAMRESTORE-1
      regressions and reproduced with `apps/web/src/viewport/**` reverted to the
      tip, so it is not that change: after `parkThenClick` on a drawn corner the
      selection readout never reaches "1 pt", i.e. the PICK does not land. 3 runs
      of 3, and still red at `4d359dd`. The pick path was changed by the SEL-2
      commits (`f4273d3`, `4009042`, `replacementPick`), which is the first place
      to look. ACCEPTANCE: green, with the cause named rather than the assertion
      loosened. agentType: frontend-builder.
      NB the same sweep found `sheet-metal-hem-corner-relief.spec.ts` red on a
      strict-mode collision with `4009042`'s new `data-disabled-reason` spans —
      already fixed upstream by `b9a77c5` and re-verified green here, so it is
      recorded rather than filed.

- [ ] (P3, XS) **FLAKE-SEL4-DRILL-1 — `qa-sel4-verify.spec.ts` "a click on a
      DIFFERENT face does not move the drill point" failed once inside a
      24-case batch and passed 2 of 2 in isolation.** kind: flake. The fixture
      is API-seeded and never enters the sketcher, so it is out of reach of both
      2026-09-04 viewport changes; recorded so the next sighting has a prior
      rather than starting a fresh hunt. It picks the FIRST raster-order lit
      point that fails a hover probe, which is a silhouette-edge point by
      construction — the same derivation that was making `founder-picking`'s
      face-seat case red, so an interior-point filter is the likely fix.
      agentType: qa-tester.

- [ ] (P2, XS) **SOLVE-CONFLICT-MOVED-1 — a `conflicting` payload can ship
      geometry the solver MOVED, which the DTO promises it never does.** kind:
      defect (contract). MEASURED by PBT-1's sweep: **2 of 2000**.
      `SolvedSketch.entities` documents "for conflicting/diverged sketches the
      input positions are returned unchanged", and `solve()` honours it for a
      diverged solve and for a payload the residual gate reclassifies — but when
      planegcs itself diagnoses a conflict on a solve that CONVERGED, the branch
      falls through to `read_back()`. So a client told "conflicting" is handed
      moved geometry, and the UI's revert-to-input assumption is wrong for those
      cases. FIX: either return the input on that branch (matching the doc) or
      change the doc; one line either way, but it is a contract decision.
      Recorded as an executable live limit, bounded both ways.
      **RE-VERIFIED unchanged, groom pass 19 (2026-08-29): SOLVE-CRASH-1 moved
      the sweep's solvable/conflicting census (1327->1328, 276->287) but this
      finding's own count is independent of that reclassification and still
      reads "2 of 2000" verbatim in `test_sketch_solver_sweep.py`'s own
      docstring/test comment — no correction needed.**
      [src: PBT-1 sweep, kernel-architect 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`,
      `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType: kernel-architect.

- [ ] (P2, S) **SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 — `status="overconstrained"`
      does not tell a client whether the entities beside it are SOLVED or the
      input returned unchanged, and both happen.** kind: defect (contract).
      MEASURED by PBT-1's sweep: of 282 overconstrained payloads, **17 returned
      the input** and 265 carried solved geometry. `_map_status` puts `redundant`
      ABOVE `not solved` in precedence, so a DIVERGED solve with a redundant
      constraint is reported as `overconstrained` — the divergence is masked,
      and the DTO's own hedge ("consistent overconstrained cases") is the only
      hint that the two exist. Consequence: no consumer can decide whether to
      adopt the returned coordinates, which is exactly the decision the sketch
      UI makes on every solve. FIX options: a separate status, or a boolean on
      the payload saying whether the entities were solved. This is why PBT-1's
      sweep excludes `overconstrained` from its solved population — an ambiguity
      in the contract becomes an ambiguity in every gate written against it.
      **RE-VERIFIED unchanged, groom pass 19 (2026-08-29): the overconstrained
      population (282, of which 17 are the input) is untouched by
      SOLVE-CRASH-1's fix — none of the twelve crashing trials were
      overconstrained — confirmed against the current
      `test_sketch_solver_sweep.py` source.**
      [src: PBT-1 sweep, kernel-architect 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`,
      `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType: kernel-architect.

**HEM-1C is CLOSED (2026-08-28, frontend-builder) — the hem card now derives
every number it shows from the hem rule instead of a stale base-flange claim,
and the override guidance states only values the evaluator accepts. New live
`Gap` readout. Ratios live in one place, pinned against the py-kit source by
a unit test. Mutation-tested three independent ways. See Done archive.**

**HEM-1D is CLOSED (2026-08-28, frontend-builder) — a Closed/Open segment now
authors the shape (`buildHemParams` sends the user's choice, was hardcoded
`closed`); asserted on the BUILT BODY (open hem stands 6.0 mm vs closed's
4.2 mm), not a 2xx. Fixes the `check-ui-parity.py` false-positive direction
CHECKUIPARITY-FP-1 (below) also names. See Done archive.**

- [x] (P2, S) **HEM-1B — CLOSED (frontend-builder, 2026-09-04). The gated Save
      now says why, and "override checked with no value" is no longer a state a
      click can reach.** The reported HYDRATION bug did not reproduce at HEAD
      and the probe says why: the server stores `k_factor: null` for an
      inherited K, and `formFromHemParams` already reads that as unchecked —
      re-opening the orphaned hem gave `aria-checked="false"`, no K field, Save
      ENABLED. What DOES reproduce, in two clicks, is the audit's screenshot:
      ticking an override left the field blank, and blank is "pending" to every
      field validator, so Save went `aria-disabled="true"` with `title: null`
      and nothing on screen. Fixed at both ends — `hemSubmitBlocker` is now the
      single source of the gate AND its sentence (`canSubmitHem` is defined as
      "no blocker", cross-checked against `buildHemParams` over 66 form/pick/
      anchor combinations), and ticking an override SEEDS the field from the
      value it replaces. The action row also moved into `EditorCard`'s pinned
      footer: at 1280x800 the reason's own centre hit-tested to
      `feature-tree-section`, i.e. the explanation had fallen out of the card.
      Survey filed as REASON-GATE-1 below (15 of 16 editor commit actions have
      the same silence). Mutation evidence, gates and the before/after shots:
      `docs/CHANGELOG.md`.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-26, split from HEM-1 by backlog-groomer pass 16]

- [x] (P1, M) **REASON-GATE-1 — 15 of the 16 editor commit actions can go grey
      with no reason on screen, which is HEM-1B repeated once per verb.** kind:
      defect (generalised from HEM-1B's second half, measured 2026-09-04 while
      closing it). `PanelActionCell` has carried a `disabledReason` prop since
      UI-REVIEW 2026-07-30 — it takes the caption's line while gated and is
      wired as the button's `aria-describedby` — and only `hole-submit` and
      (now) `hem-submit` pass it. The other fifteen (`base-flange`, `chamfer`,
      `combine`, `corner-relief`, `datum`, `draft`, `edge-flange`, `extrude`,
      `fillet`, `loft`, `mirror`, `pattern`, `revolve`, `shell`, `sweep`) share
      the exact `canSubmitX(form, …) && !saving` -> `disabled={!canSubmit}`
      shape the hem had, so every "no pick / no body / empty override" state is
      a silent dead end there too. The TOOLBAR tier is fine by contrast and is
      the model to copy: 41 of 43 gated `ToolButton`s carry a gate-aware
      `caption` ("Add a base flange first"), the two exceptions being
      `add-instance` (no caption) and `sketch-discard-confirm` (a constant one).
      FIX: give each editor a `*SubmitBlocker` in its feature module, define
      `canSubmitX` as `blocker === null` so the two cannot drift, and pass it as
      `disabledReason` — the shape `HemEditor` + `apps/web/src/features/
      sheetMetal.ts` now demonstrate. Keep each string ≤48 chars: the footer
      cell is half a card wide (~19 chars a line) and a 74-char sentence
      measured five wrapped lines. ACCEPTANCE: a property test per editor —
      across every way its form can be invalid, a gated submit carries readable
      text AND that text is its accessible description; plus one e2e case
      proving it at 1280x800 with `elementFromPoint`, because a footer that is
      not pinned puts the sentence outside the card (measured on the hem).
      TERRITORY: `apps/web/src/components/*Editor.tsx` +
      `apps/web/src/features/*.ts`. agentType: frontend-builder.
      **CLOSED 2026-09-04 (frontend-builder), and the acceptance grew one clause
      the ticket did not ask for.** All fifteen have an `xSubmitBlocker` with
      `canSubmitX` defined as `blocker === null`; `fieldBlocker` in the new
      `apps/web/src/features/submitBlocker.ts` is the one shared piece (the
      blank-vs-wrong pair, fifteen real uses) and `edgeSelectorBlocker` the
      second (fillet + chamfer). Evidence in three layers: 84 unit cases
      cross-checking every blocker against the PRE-change predicate restated
      literally (asking `canSubmitX` would be the new code agreeing with
      itself), with floors of 15 subjects / >=2 gated states each / >=50 gated
      total; a per-editor DOM case for all SEVENTEEN with the count asserted;
      and 10 editors measured in real pixels at 1280x800 with `elementFromPoint`
      resolving to their own Save cell. THE CLAUSE THAT GREW: every one of the
      fifteen action rows also had to move into `EditorCard`'s pinned `footer`.
      That slot has existed since UI-REVIEW 2026-07-30 P1 and only hole + hem
      used it, so a reason line — which makes each card taller — would have
      shipped the defect in a longer form; `docs/screenshots/reason-gate-draft-
      before-1280.png` shows the CREATE row half-clipped at the fold with
      nothing said. Mutation evidence: deleting `disabledReason` from ONE editor
      reddens exactly its own case and leaves sixteen green; un-pinning ONE
      footer reddens only that case. The e2e suite caught a copy defect the unit
      tests could not — the corner relief's first reason repeated its own
      FIELD's inline error verbatim, so the same sentence rendered twice on one
      card (a `getByText` resolved to two nodes); it now says "Choose a
      different flange for bend B." 2271 web + 141 design unit tests, 109 e2e.
      [src: HEM-1B survey, frontend-builder 2026-09-04]
      **STRAGGLER CLOSED groom pass 27 (`17763b5`):** `OffsetPlanePanel`
      (the sketch flow's inline datum-offset form) was never one of the 15
      editors this rollout enumerated — it gates `SketchStrip`'s commit
      button, not an `*Editor.tsx` module — so it kept a native `disabled`
      with no `aria-describedby` and dropped out of the a11y tree while
      gated. Now asks the same `datumSubmitBlocker({kind:"offset",...})` the
      datum editor uses and renders through the editors' own
      `PanelActionCell`. `offset-plane-reason.spec.ts` 2/2, red on the
      pre-fix tree.

- [ ] (P2, M) **QA-R3 — on touch, four of REACH-1's five new verbs cannot be
      reached at all, because a tablet cannot select two entities.** The rail's
      keycaps are real buttons and tapping one works (tap `verb-hint-angle` ->
      the editor opens -> 30 deg applies). The block is upstream: a plain second
      tap REPLACES the selection and a 900 ms long press (dispatched as a real
      touch sequence over CDP) does the same — additive selection is Shift-click
      only. Measured: `TOUCH-ADDITIVE {"plain":"1 ent","held":"1 ent",
      "offers":["verb-hint-distance"]}`, so the rail can only ever propose
      single-entity verbs there and angle / collinear / symmetric_lines /
      midpoint are unreachable. Diameter (single-entity) is fine. ACCEPTANCE: a
      touch-native additive gesture (tap-adds while a verb is armed, a long-press
      toggle, or a visible "add to selection" affordance) gets two entities
      selected on a `hasTouch` context, and `verb-hint-angle` appears; qualify
      `scripts/check-ui-parity.py`'s count as desktop-only, or count per surface.
      [src: docs/QA-REVIEW.md 2026-08-27 QA-R3, filed by qa-tester]
      **STILL OPEN, groom pass 16 — this could only be measured by hand
      (ad hoc `hasTouch` contexts per-spec), because `playwright.config.ts`
      defines no touch project at all; see PLAYWRIGHT-TOUCH-1, filed this
      pass, for the harness gap this and every future touch finding hits.**
      TERRITORY: `apps/web/src/viewport/SketchScene.tsx`, `apps/web/src/sketch/**`,
      `apps/web/e2e/qa-reach-batch.spec.ts`. agentType: frontend-builder.

- [ ] (P2, S) **PLAYWRIGHT-TOUCH-1 — the e2e harness has no touch project,
      so the "touch" half of the QA remit is measured by hand every time.**
      kind: capability (test infra). MEASURED: `apps/web/playwright.config.ts`
      defines a single default project with no `projects` array at all — no
      device emulation, no `hasTouch`/tablet profile. Every touch finding to
      date (QA-R3 here, plus the `hasTouch`-context probes scattered across
      `full-flow.spec.ts`, `import-remix.spec.ts`,
      `measure-pattern-qa.spec.ts`, `qa-reach-batch.spec.ts`,
      `qa-sel4/6/7-verify.spec.ts`) hand-rolls its own `browser.newContext
      ({ hasTouch: true })`, so touch coverage depends on an individual spec
      author remembering to add one — there is no standing CI signal for
      "does this regress on touch" the way there is for desktop. FIX: add a
      `projects` entry (e.g. a tablet viewport with `hasTouch: true`,
      `isMobile` as appropriate) so touch-relevant specs can opt in via
      `test.describe.configure`/project filtering rather than each
      hand-rolling a context; consolidate the existing ad hoc `hasTouch`
      probes onto it where practical. ACCEPTANCE: a `--project=touch` (or
      equivalent) run exists and is documented; at least the existing
      touch-relevant specs run under it; a deliberately broken touch
      affordance fails the touch project without needing a bespoke context
      in the spec.
      [src: backlog-groomer pass 16, cross-referencing QA-R3's "measured by
      hand" note]
      TERRITORY: `apps/web/playwright.config.ts`, `apps/web/e2e/*.spec.ts`
      (consolidation only, no product code). agentType: frontend-builder.

- [x] (P2, S) **CLOSED (frontend-builder, 2026-08-29) — the field MOVED rather
      than the call site being remembered.** `mateErrors` now lives on
      `AssemblySolve`, empty whenever `stale`, and `AssemblyTreePanel` takes
      `solve` instead of the raw `EvaluateAssemblyResult`, so it has nothing
      ungated left to read (it was reading `diagnosis.conflicting_mates`
      directly too, which the ticket did not name). A field that is not on
      `AssemblySolve` is a field a consumer can read raw — that, not another
      call-site audit, is what stops a ninth. Rows carry `data-mate-state`
      (`ok`/`conflict`/`unresolved`/`pending`) so "no fault" and "not yet
      known" are distinguishable. The matrix gains the consumer in three
      places: the seven superseded-path rows, the 2^6 invariant over all 63
      stale combinations, and the ONE settled combination asserting
      `mateErrors` has length 1 — without which "empty whenever stale" would
      hold in a build where the field is always empty. Measured on the real
      stack at 25 ms across a superseding write:
      `pre-write [conflict,conflict] inked=2` -> `t+0 stale=true
      [pending,pending] inked=0` -> `t+861 [conflict,conflict] inked=2`.
      Mutations, each reverted: panel back on the raw evaluation -> 2 rows
      badged over a superseded solve at t+612/779/898 ms, by attribute AND by
      ink; `mateErrors` ungated -> 8 of 13 matrix cases fail. Gates: `just
      lint` 0, `pnpm -r test` 2291, 28/28 across eleven assembly/mate specs.
      **MATE-OBS-2 — `AssemblyTreePanel` badges mates from
      `evaluation.mate_errors`, so it can carry a superseded solve's error
      set through the same staleness window MATE-OBS closed.** kind: defect
      (same family as MATE-OBS, `6b26ff7` — that fix made `evaluation` null
      whenever `stale`; this is a consumer that still reads the field
      directly rather than through the staleness-checked accessor). Found
      while verifying `6b26ff7`'s "SEVEN paths" list — the tree panel's mate
      badge was not one of the seven audited call sites. UNDER-claims rather
      than over-claims (a badge could show a stale error, or fail to show a
      real one, for the same ~600-840 ms window), which is why it is P2 not
      P0/P1 like MATE-OBS was. FIX: route `AssemblyTreePanel`'s badge
      through the same `stale`-gated accessor `6b26ff7` introduced for the
      solve title block, rather than reading `evaluation.mate_errors`
      directly. ACCEPTANCE: a mate write in flight shows no badge (or a
      clearly "pending" one) rather than the pre-write error set; the
      `6b26ff7` staleness matrix gains this consumer as an eighth case.
      [src: MATE-OBS (`6b26ff7`) follow-up, filed by backlog-groomer pass 15]
      TERRITORY: `apps/web/src/components/AssemblyTreePanel.tsx`,
      `apps/web/src/features/assemblySolve.ts`. agentType: frontend-builder.

- [ ] (P2, S) **STAGE-DOC-HUNKS-HEADING-1 — `stage-doc-hunks.py` truncated a
      BACKLOG entry again, this time on a heading-immediately-followed-by-
      list-item boundary its own fixtures cannot reach.** kind: defect
      (tooling — the fourth silent failure of this script, all four
      catalogued in CLAUDE.md's staging-protocol section; this is a new
      TRIGGER for the same "invented boundary" failure mode CLAUDE.md already
      records for a bold-continuation line). MEASURED: the PANEL-DENSITY-1
      agent's marker landed on a `###` heading, and the entry's own BODY was a
      `- **ID**` list item directly beneath it — `ENTRY_START` reads a list
      item as always starting a new entry, so it split the agent's own
      10-line body off from its heading and staged only the heading, printing
      `left 0 hunk(s) unstaged` while the body sat unstaged for nobody (the
      agent, not a colleague, so nothing was swept — but the commit shipped
      with a decapitated entry until caught by `git show :docs/BACKLOG.md`,
      the doc-hygiene check the staging protocol already mandates). FIX: teach
      `ENTRY_START` (or the cross-check) that a list item directly beneath a
      heading with no intervening blank line continues that heading's entry
      rather than starting a new one — the same "an entry boundary only opens
      where an entry CAN begin" principle the bold-continuation fix already
      applies, extended to the heading+list-item shape. ACCEPTANCE: a
      `--self-test` fixture reproduces this exact shape (a `###`/bold heading
      immediately followed by a `- **ID**` list-item body, both added in one
      hunk, one marker on the heading line) and demands the heading+body stage
      together; the existing three fixtures (plain BACKLOG list items, bold-lead
      ROADMAP paragraphs, bold-continuation) are unaffected; the cross-check's
      negative control still refuses on a deliberately-reverted boundary rule.
      [src: PANEL-DENSITY-1 agent report, 2026-08-28, reproduced via
      `git show :docs/BACKLOG.md` after the fact]
      TERRITORY: `scripts/stage-doc-hunks.py`. agentType: platform-builder.

**DRAWING-VERTEX-PICK-1 is CLOSED (`fe96d9b`, groom pass 16) — a vertex now
claims at most a third of its shortest incident edge (`vertexGrabMm`), so the
edge reclaims the band it lost. See Done archive.**

- [ ] (P2, S) **SKETCH-COVERAGE-1 — `equal` and `tangent` constraints have
      no e2e driving them through the UI; they are reachable but nothing
      proves it.** kind: defect (test gap, on the class CLAUDE.md's params-
      extra-ignore recipe warns about: a UI path that silently regresses is
      indistinguishable from one that never worked). `SKETCH-VOCAB-1`
      closed the five verbs that were genuinely unauthorable
      (angle/diameter/midpoint/collinear/symmetric); `equal` and `tangent`
      predate that work and are believed reachable from the existing
      constraint menu, but a repo-wide spec search found no e2e case
      authoring either through the sketch UI (verify against
      `apps/web/e2e/sketch-*.spec.ts` before writing — do not assume the
      gap is real without re-checking, the same discipline `PATTERN-1`'s
      params-typo lesson demands). ACCEPTANCE: one e2e case per verb,
      authoring it through the real UI (not a fixture pre-loaded with the
      constraint), asserting the solved result changes as expected and the
      constraint round-trips through save/reload; if either verb turns out
      to be genuinely unreachable, re-file as a P1 capability gap instead.
      [src: backlog-groomer pass 15, cross-referencing SKETCH-VOCAB-1's
      closure]
      TERRITORY: `apps/web/e2e/` (new spec cases), `apps/web/src/sketch/**`
      if a real gap is found. agentType: frontend-builder.

- [ ] (P3, XS) **SOLVER-DOC-1 — `solver.py`'s docstring claims the null
      space "stays anchored at the seed," and measurement says otherwise.**
      kind: defect (documentation accuracy — CLAUDE.md: "a claim that is not
      true is a defect here, including in a comment"). MEASURED (`1ae3270`'s
      own investigation, deliberately NOT asserted in that gate): the LM
      solver slides a mated bracket ~0.015 mm laterally inside the mate's
      null space — deterministic, and not incorrect (those DOF are
      genuinely free), but it contradicts the docstring's anchoring claim.
      FIX: correct the docstring to describe what the solver actually does
      (converges to A solution within the null space, not necessarily the
      seed) rather than what was assumed. ACCEPTANCE: the docstring's claim
      matches `1ae3270`'s measurement; no behaviour change.
      [src: `1ae3270` commit investigation, filed by backlog-groomer pass 15]
      TERRITORY: `services/geometry/src/geometry/assembly/solver.py`
      (docstring only). agentType: kernel-architect.

- [ ] (P2, S) **FLOW-POLISH-1 — four small flow-capture defects from the
      fourth product-audit pass, bucketed to keep the board a workable
      size.** Each independently shippable; pull by finding id and re-
      derive acceptance from the finding text. **P1** — a `422` with a
      `details[]` array renders as the generic envelope message
      ("Request validation failed") instead of the per-field reason the
      gateway already returns (T-2: registering `audit4@loft.test` fails
      with no indication the problem is a reserved-TLD email — the exact
      first interaction an air-gapped-shop evaluator would have). **P2** —
      after a drag-drawn rectangle, `document.activeElement` is `BODY`
      instead of the size cell 800px away in the corner that reads "Type a
      size" (T-4, half of FB-16's "capture intent where it forms" promise);
      the selection readout counts entities (`3 ents`) but never names
      them, so a refused selection (e.g. Symmetric wanting points, not
      edges) gives no way to tell what was actually picked without
      screenshotting the viewport (T-6); circular-edge aria-labels report
      the CENTRE MINUS THE RADIUS, not the centre (T-12: four holes at the
      provably symmetric ±23.5,±23.5 are labelled at the asymmetric -26.7
      and +20.3 — reads as a modelling error in a part that is correct).
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-24 (fourth pass)"
      T-2/T-4/T-6/T-12, filed by backlog-groomer pass 11]
      TERRITORY: varies — auth error rendering (T-2), sketch drag-draw
      focus (T-4), selection readout (T-6), edge-pick aria-label
      generation (T-12), all `apps/web/**`. agentType: frontend-builder.

- [ ] (P2, M) **IMPORT-HEAL-1 — a STEP import yielding zero solids has no
      recovery path.** kind: capability. `geometry.kernel.imports` says
      plainly "It does not sew/heal/repair, and IGES is deferred." Real
      supplier/legacy STEP frequently arrives with gaps, tiny faces, or open
      shells; a file yielding zero solids returns `import_no_solid` with NO
      recovery — no "import as surfaces", no "attempt to sew", no partial
      result. Preserve the audit's framing: this is the more SEVERE gap
      (an unrecoverable dead end — with a missing export format you convert
      elsewhere, with a dead import you cannot start at all) even though the
      audit ranks it P2 by COST against the near-zero DXF/3MF/glTF wins in
      Ready — that tension is deliberate, not an oversight. FIX: attempt
      OCCT `ShapeFix`/`ShapeUpgrade` sew+heal before returning
      `import_no_solid`; on success, the response carries a `repaired: true`
      flag naming what was fixed (faces stitched, gaps closed). ACCEPTANCE:
      a golden fixture with a small controlled defect (e.g. one face split
      by a hairline slit) imports successfully post-fix where it failed
      pre-fix; a genuinely unrecoverable fixture (no closed volume possible)
      still returns `import_no_solid` unchanged — negative control.
      [src: AUDIT-PRODUCT.md F-6.1, ranked #6, 2026-08-17 pass]
      TERRITORY: `services/geometry/src/geometry/kernel/imports.py`,
      `services/geometry/src/geometry/kernel/_step_parse_worker.py`.
      agentType: kernel-architect.

- [ ] (P2, S) **IMPORT-HEAL-2 — surface the healing report / partial-result
      honesty in the import UI.** kind: capability. Depends on
      IMPORT-HEAL-1's response shape landing first. ACCEPTANCE: when the
      import response carries `repaired: true`, the import UI shows an
      honest notice naming what was repaired rather than a silent success.
      [src: AUDIT-PRODUCT.md F-6.1, 2026-08-17 pass]
      TERRITORY: `apps/web` (the existing STEP-import flow, `CreateStrip`'s
      Import button). agentType: frontend-builder.

- [ ] (P2, XS) **EXPORT-ERR — an unsupported export format returns a raw
      pydantic `literal_error` instead of a typed
      `export_format_unsupported`.** kind: defect. Measured
      (`docs/AUDIT-PRODUCT.md` F-7, 2026-08-17): asking for a format outside
      `ExportFormat`'s literal (3MF/glTF have since shipped via EXPORT-2 and
      no longer trigger this — the example is stale, the underlying gap
      isn't: try `dwg` or `obj` today) gets
      `{"type":"literal_error","loc":["body","format"],"msg":"Input should
      be 'step', 'stl', '3mf' or 'glb'"}` — correct, but reads like a schema
      violation rather than "not built yet," which matters for anyone
      driving the API from a script or an agent. ACCEPTANCE: a typed error
      naming the
      supported-formats list, using `py-kit`'s existing error envelope,
      replaces the raw pydantic error on both export enums (`ExportFormat`,
      `ArtifactFormat`); test asserts the error `type` and a `supported`
      field.
      [src: AUDIT-PRODUCT.md F-7, 2026-08-17 pass]
      TERRITORY: `packages/py-kit/src/py_kit` (error envelope),
      `services/gateway/src/gateway/features.py` or the geometry export
      route. agentType: backend-builder.

- [ ] (P2, XS) **SOLVE-2 — the feature-tree panel's SOLVE cell and the
      sketch DRO's SOLVE cell can read `Solved` and `DOF 6 ·
      UNDER-CONSTRAINED` simultaneously, on the same screen, for the same
      sketch.** kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` R-3,
      2026-08-21 pass): both are technically true (the solve converged; six
      DOF remain) but a user scanning "is this locked down?" gets a yes and
      a no at once, ~500px apart, with no cue which cell answers the
      question. Incumbents publish ONE status. FIX: the tree cell should
      carry the DOF verdict too, or drop the word SOLVE there and say
      `Converged`/`Failed`. ACCEPTANCE: the two cells no longer present
      contradictory verdicts for the same sketch state; unit test on the
      tree cell's label given an under-constrained-but-converged sketch.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-3, filed by
      backlog-groomer pass 8]
      TERRITORY: `apps/web/src/routes/PartPage.tsx` (feature-tree SOLVE
      cell). agentType: frontend-builder.

**PATTERN-1 is SHIPPED (`ec9c569`) — see Done archive for evidence/gates.**
Its own design review found four flow gaps the builder did not catch; filed
below as REACH-2-FLOW rather than reopening PATTERN-1 itself.

**REACH-2-FLOW is CLOSED (2026-08-28, frontend-builder) — the pattern-scope
proposal now has a channel the icon tier cannot shed (a `BandStateCell`
primitive outside any `ToolGroup`, 104px painted vs 0px for the shed Modify
label), three surfaces echo the subject (tree stamp, timeline chip, viewport
tint via `usePublishedScope`), Cancel/Escape no longer destroys the
triggering selection, and the row's context menu offers `Repeat`/`Mirror`
directly so selecting a pattern seed no longer requires opening and
dismissing its editor first. Mutation-tested per sub-defect. Two halves
deliberately deferred, not forgotten — REACH-2-FLOW-B (viewport highlight
should follow command scope, not just selection) and REACH-2-FLOW-C (tree
select/edit split + band budget) below. See Done archive.**

- [x] (P2, S) **REACH-2-FLOW-B CLOSED (2026-09-04, frontend-builder) — the
      viewport tint now answers the COMMAND's question, and the three surfaces
      agree.** The tint read `selectedFeatureId`, so it went on saying `Hole1`
      after the user flipped the scope row to `This body` and said nothing when
      the editor seeded from the TIP with nothing selected. `viewport/
      scopeHighlight.ts` is the one rule both cases read; `PartPage`'s
      `selectedFaceIndices` filters the overlay by that set. THE FIX IS A THIRD
      STATE, not a fallback on emptiness: `scopedFeatureIds` was
      `readonly string[]` where `[]` meant BOTH "the whole body" and "nobody is
      asking", which the tree and timeline can conflate (no fallback, same
      absence) and the viewport cannot — it is now `readonly string[] | null`.
      `This body` paints NOTHING, chosen: a highlight is a differencer, so a
      full-body brass would hide the machined read, collide with the distinct
      whole-body SELECT state, and carry as much information as none. Measured
      in painted pixels (warmth census — the tint MULTIPLIES the matcap, so no
      literal hex describes it), same camera either side of the flip: scoped
      **384** warm px / `data-selected-faces` 1, `This body` **0** / 0, and
      tip-seeded with nothing selected **473** / 1. Mutation-tested per half:
      the pre-fix reading gives 384/1 on `This body` (the tint that would not
      let go) and 0/0 tip-seeded (the tint that never arrived). Screenshots:
      `docs/screenshots/reach2b-scope-{body,tip}-{before,after}-laptop.png`.

- [ ] (P2, M) **REACH-2-FLOW-C — the feature tree has no gesture that
      selects WITHOUT entering a command, and the band is out of room at
      1280.** kind: defect (flow). Two findings from REACH-2-FLOW that are
      each too large to be a clause of it, with the measurements that size
      them. (1) **The select/edit split.** `selectFeature` unconditionally
      opens the row's editor, which locks both the band (`sr-only`) and the
      accelerators, so "select Hole1, press Pattern" really costs an
      Escape. Fusion/Onshape/SolidWorks all separate single-click-selects
      from double-click-edits, and our row button is already NAMED
      `Select <name>`, so the destination is not in doubt. The cost is: **75
      references across 28 e2e spec files**, roughly half of which click a
      row expecting an editor — a re-training event for every existing flow,
      not a sub-clause. REACH-2-FLOW shipped the narrow half instead (the
      row's context menu offers `Repeat`/`Mirror` directly, so the toll is
      gone for the seed gesture) and this is the general fix. Ship the
      second affordance in the SAME commit or editing becomes undiscoverable:
      double-click, Enter on the focused row, and the existing
      `tree-ctx-edit`. (2) **The band's budget.** Measured at 1280x800: the
      resting row is 1241px of 1280, i.e. **39px of slack**, and the label
      budget affords exactly EXPORT (+160) and INSPECT (+37). Any
      always-visible cell therefore drops the band to the icon tier —
      REACH-2-FLOW's 104px scope cell does, costing EXPORT its format codes
      while a scope is held (it gets them back the moment the cell's `x` is
      pressed, measured). `CommandBand`'s own doc names the fix: an explicit
      overflow flyout. A cheaper prize sits beside it — SHEET METAL is 215px
      of icons for a family "inert on every part that is not sheet metal".
      ACCEPTANCE: (1) a tree row can be selected without opening its editor,
      and editing is reachable by at least two visible gestures; (2) holding
      a scope at 1280x800 no longer costs EXPORT its labels.
      [src: REACH-2-FLOW build, 2026-08-28, frontend-builder]
      TERRITORY: `apps/web/src/components/FeatureTreePanel.tsx`,
      `apps/web/src/routes/PartPage.tsx`, `packages/design/src/primitives/
      CommandBand.tsx`, `apps/web/e2e/**`. agentType: frontend-builder.

**ORTHO-1 is CLOSED (`9a04a6a`, groom pass 16) — an ORTHO/PERSP toggle in the
view rail; orienting commands (Home/Front/Top/Right/Iso, their accelerators,
ViewCube picks) arm orthographic, Fit does not change it, orbiting away from
a named view keeps it. Closes a gap four consecutive audit passes reported
(M18/R-11/S-31/T-20). See Done archive.**

**HEM-1 is CLOSED (`db05e13`, P0, groom pass 17) — a "closed" hem's radius now
comes from the hem type and gauge (~0.5x thickness), not the part's general
bend radius. See Done archive for evidence/gates.**

- [x] (P1, S) **CLOSED (frontend-builder, 2026-08-29) — RENDERING ONLY; the
      server already sends this typed, so no larger ticket is owed.**
      `AssemblySolveDiagnosis` carries `classification`, `conflicting_mates`,
      `redundant_mates`, `remaining_dof`; `message`/`suggested_fix` are prose
      built ALONGSIDE them and the panel was printing the prose. Nothing in
      `services/geometry` changed. `apps/web/src/assembly/diagnosis.ts`
      composes the sentence from the typed fields and never reads `message`,
      naming mates through `mateNamesById` — the same derivation the tree
      prints on the row, so a raw id can never be the only handle because it is
      never printed at all (an id with no row is COUNTED, never printed).
      `sentence()` terminates each clause before joining, closing (c) here and
      on the healthy path. Mates gained the handle they lacked: `M1`, `M2` … in
      a squared tag (components are balloons/circles; a joint is not a part),
      numbered in the solver's own processing order, not `aria-hidden`, and the
      row's Remove is now `Remove M2 Coincident` so two mates of one kind no
      longer share an accessible name. The "remove this one" action ships HERE
      rather than as its own item — the handler existed and the message is one
      line above it; the chip spends the tag only (`Remove M1`, full form as
      accessible name) because the longer label stacked the chips and pushed
      BOUNDING BOX below the fold at 1280. Gates: 19 unit + 3 e2e new,
      `just lint` 0, `pnpm -r test` 2290, 24/24 across eight assembly specs.
      Mutations, each reverted: server prose restored -> the e2e reproduces the
      reported string verbatim; visible tag deleted with `data-mate-tag` kept ->
      the findability case fails on the INK, not the attribute; `sentence()`'s
      terminator dropped -> 11 of 19 unit cases fail with the exact run-on.
      Frames: `docs/screenshots/mateui1-before-1280.png` /
      `mateui1-after-1280.png`.
      **MATEUI-1 — the mate-conflict diagnosis prints a Python
      `repr` of a UUID list to the user, and names a mate the UI cannot
      identify.** kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` "Pass
      2026-08-21 (second pass today)" S-18), verbatim from the SOLVE tab
      with two conflicting Coincident mates: `mates [UUID('4ae95465-...'),
      UUID('b78a814e-...')] are mutually unsatisfiable Remove or relax
      mate 4ae95465-...` — (a) a raw list-of-UUID repr leaked into
      user-facing UI; (b) the named mate appears NOWHERE in the mates
      panel (both rows read identically as "Coincident · ①1 · ②2 ·
      conflict"); (c) two sentences concatenated with no separator — same
      missing-separator bug on the healthy path too ("...remain; free
      instances left at their seed placement Add mates to..."). FIX:
      render the typed diagnosis as data — name mates as they appear in
      the panel (or add a distinguishing label so a UUID isn't the only
      handle), fix the missing sentence separators everywhere they occur,
      add a "remove this one" action next to each named mate. ACCEPTANCE:
      the conflict message names mates by their panel-visible identity,
      not a UUID repr; a unit/snapshot test on the message-assembly
      function catches a reintroduced missing separator.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-18, filed by backlog-groomer pass 9]
      TERRITORY: assembly mate-conflict diagnosis rendering, `apps/web/src`
      (assembly inspector SOLVE tab) + `services/geometry/src/geometry/
      assembly/**` (message assembly, if server-formatted — check first).
      agentType: frontend-builder (or backend-builder if the string is
      assembled server-side).

- [x] (P1, XS) **CLOSED BY MEASUREMENT (frontend-builder, 2026-08-29) — DOES
      NOT REPRODUCE ON HEAD; T-18's `ScrollRegion` (`a67f4bc`) and the density
      pass (`54d12bf`) had already fixed it and nobody re-measured, so this was
      one groom pass from being fixed twice.** Re-measured at 1280x800 on the
      audit's own subject (150x80x8 plate, steel assigned): band y=112..474.5,
      strip y=474.5..590 — **abutting at 0.0 px against the reported 73 px
      overlap** — and all 8 on-screen rows resolve to THEMSELVES under
      `elementFromPoint`, `Extents` included. The 137 px below the fold is
      clipped, marked and keyboard-reachable (T-18's shipped answer). NOTE the
      trap: a naive rect-vs-rect sweep "reproduces" this on a healthy panel,
      because a row below the fold keeps its layout rect — 8 of 10 rows report
      an overlap that is only a scroll away. Shipped instead: the ticket's own
      acceptance criterion as a permanent clip-aware gate in
      `apps/web/e2e/inspector-scroll.spec.ts` (band/strip never intersect;
      strip never hangs past the panel; every on-screen row answers to itself;
      count floor 6 against a vacuous pass). Two mutations, each reverted and
      each with Vite restarted + served bytes re-read, turn it red — the
      `FloatingPanel`-footer one reproduces the audit verbatim (`prop-faces`
      on screen, `elementFromPoint` → `part-export-controls`). No product code
      changed. Frames: `docs/screenshots/layout1-reported-defect-1280.png` vs
      `layout1-inspector-1280.png`.
      **LAYOUT-1 — the inspector panel
      overlaps its own content at
      the documented responsive floor (1280x800), violating CLAUDE.md's
      stated quality floor directly.** kind: defect. MEASURED
      (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" S-29):
      `getBoundingClientRect` at 1280x800 — `BOUNDING BOX` section
      y=410…532, export band (`part-export-controls`) y=459…590, a 73 px
      overlap; the `Extents` row is half-covered by `EXPORT Ready`. Min,
      Max, Faces, Edges, Shells, Status are unreachable. FIX: resolve the
      layout collision (stack, scroll, or resize) at 1280x800. ACCEPTANCE:
      a layout assertion (Playwright bounding-rect check, mirroring S-29's
      own method) at 1280x800 confirms zero overlap between the
      inspector's sections; visual regression screenshot at that width.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-29, filed by backlog-groomer pass 9]
      **THIRD CORROBORATION, groom pass 11 (2026-08-24): T-18 (fourth
      product pass) re-measured the identical overlap on a finished part —
      `Min` row at y 474..491, export panel at y 459..589,
      `elementFromPoint(985, 482)` returns the Export panel's own `SPAN`,
      and walking the ancestor chain finds NO `overflow: auto|scroll`
      container, so the content is unreachable by scrolling either.** [src:
      docs/AUDIT-PRODUCT.md "Pass 2026-08-24 (fourth pass)" T-18]
      TERRITORY: apps/web inspector panel component (grep `part-export-
      controls` / `BOUNDING BOX` section). agentType: frontend-builder.

- [x] (P1, XS) **CLOSED (frontend-builder, 2026-08-29).** A body with no stop
      of its own now ghosts while a sketch is open, via a DERIVED DEFAULT
      (`partView.bodyView`) on the same contract `sketchIsDrawn` has held
      since UI-W2 — nothing is written on entry, so there is no restore step
      on exit to get wrong, and a stop the modeler SET wins at every moment
      including one set mid-sketch, which then survives the close. Applies to
      EVERY body (occlusion follows the camera and the plane, not the picked
      face); `hidden` never moves, so isolate / show-all / the ISOLATED stamp
      / pick-occlusion are untouched. One derivation feeds the Bodies row AND
      the material split, and `sketchOpen` is a required argument — which is
      what surfaced every call site at compile time. Published by
      `SketchScene` on `draw`, not `plane`. No new token (existing
      `viewport.preview.surfaceOpacity` 0.42).
      MEASUREMENT TRAP, recorded because the first draft fell in it: the
      canvas band census cannot be compared across sketch entry/exit (the
      sketcher parks the camera; BRIGHT 310289 -> 24675 with drawn=6/ghost=0
      at both ends), and the bands cannot separate ghost from solid even at
      one camera head-on (26935 vs 27299, 1.3%). The working instrument is the
      SPECULAR PEAK (lum > 210): ghosted 0/0, solid 525.
      Gates: partView unit 25/25, part-visibility 9/9, 23/23 sketch specs,
      19/19 body/pick specs, `just lint` 0, `pnpm -r test` 2270. Mutation
      (`bodyView` ignores `sketchOpen`, Vite restarted + served bytes checked)
      reddens the new e2e case and 2 unit cases. Frames:
      `docs/screenshots/ghost1-sketch-open-{before,after}.png`.
      EVIDENCE PASS (same day, follow-up): the cube pair was correct and did
      not COMMUNICATE — head-on, ~8% of frame, and the only occluder is the
      sketch's own body, so it cannot tell "ghost the host" from "ghost
      everything". Added `a NEIGHBOUR body ghosts too`: a two-body part whose
      HOST is extruded `direction: "reverse"` (behind the sheet, occludes
      nothing) with a `merge: false` bar standing in front of the profile —
      the configuration the scope decision was made for, and one a
      host-only build would fail. It orbits off the sketch normal for depth,
      and three things had to be measured: dragging into the park-ease loses
      the orbit (settles 0.02 deg from straight down, reads as an unbound
      button — wait for camera rest first); the documented (150,-110) drag
      turns 72 deg and is unreadable, (62,-46) gives 31.56 deg; and
      `waitForCameraRest`'s 0.05 deg default is unreachable against a coast
      that decays per rendered frame (0.3 deg settles). The settled pose is
      reproducible to 1e-12 and is PINNED in the spec, because the pair is
      shot in two runs and is only honest on one camera. Frames:
      `docs/screenshots/ghost1-neighbour-{before,after}.png`.
      FOLLOW-UP FILED, not fixed here: exiting a sketch leaves the camera
      parked in the sketch's TOP view instead of restoring the previous view
      (pre-existing, unrelated, found while measuring) — see CAMRESTORE-1.
      **RESIDUAL CLOSED groom pass 27 (`0d96454`):** `ModelMesh` returned
      before ghosting anything whenever a part's per-body face split
      couldn't be resolved (two bodies welded at shared coordinates —
      `bodyFaceSets` -> null), so such a part stayed fully OPAQUE over the
      sketch being edited even though the Bodies panel correctly read
      GHOST. Fixed: ghost the WHOLE mesh when no split exists and no body
      carries a stop of its own (a stored stop still wins). Pixel witness
      asserted first (bright fraction inside the plate's top face: 1.0 on
      the pre-fix tree, 0.0 after); 22/22 regression across part-visibility,
      multibody-disjoint/union and sketch-visibility.

- [ ] (P1, XS) **STEPNAME-1 — assembly STEP export names components with
      raw UUIDs instead of their part names.** kind: defect. MEASURED
      (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)"
      S-22): STEP structure is correct (1 assembly PRODUCT, 2
      NEXT_ASSEMBLY_USAGE_OCCURRENCE, exact volume) but read back through
      OCCT's XCAF reader the component labels are raw UUIDs
      (`c7ebc346-bbd5-4f55-9a01-4fce6f5fc28e`); the instance's real name
      ("Chassis bracket") is right there in the BOM and unused. Also:
      `FILE_NAME` still reads `'Open CASCADE STEP processor 7.9',
      'build123d','Unknown'` — Loft doesn't name itself in files it
      authors. FIX: use the instance/part name for each component label in
      the STEP writer; set the originating-system field to identify Loft.
      ACCEPTANCE: exporting the audit's two-part assembly and reading it
      back names both components by their part name, not a UUID; new
      golden/assertion on the STEP writer.
      **GEOMETRY HALF SHIPPED (kernel-architect, 2026-08-29); THE HEADLINE
      HALF IS NOT A GEOMETRY DEFECT.** The writer has threaded the instance
      name into the NAUO and the PRODUCT since `0d3ea59` (2026-07-31, three
      weeks BEFORE the audit) — asserted on the emitted bytes, not assumed.
      The UUID the audit read is the documented FALLBACK for a request with
      no `name`, and the caller that omits it is
      `apps/web/src/assembly/evaluateRequest.ts`, which builds
      `EvaluateAssemblyRequest` without the field the DTO has carried all
      along. That is a one-line web change in foreign territory: STEPNAME-1B.
      What WAS wrong here, found by exercising the writer rather than reading
      it, and both fixed: (a) **every non-ASCII name was corrupted** —
      `TCollection_ExtendedString(str)` binds the `isMultiByte=False`
      overload and walks UTF-8 bytes as characters, so "Flänsch" measured 17
      characters instead of 13 and reached the file double-encoded; (b) the
      originating system read `build123d`, so a file Loft authored named a
      library instead. Note (a) is why fixing the web alone would have been
      wrong: a name that is present and corrupted is not better than one that
      is absent and obvious. Duplicate part names DECIDED and pinned: two
      instances of one part correctly share one PRODUCT (the case that
      occurs); two DIFFERENT parts a user names alike keep the name verbatim
      and collide on `PRODUCT.id`, which we do not disambiguate because that
      means mangling a part number in the file a supplier quotes from. Two
      mutants, both restored: reverting the encoding reddens 8 cases (all and
      only the non-ASCII ones, on both `BodyShape` members); reverting the
      originating system reddens 1. Filed alongside: STEPNAME-1B (web),
      STEPNAME-2 (single-body path), STEPDET-1 (a determinism hole found by
      writing the test). Gates: `just lint` exit 0, `uv run pyright` clean,
      482 STEP-adjacent tests green.
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)"
      S-22, filed by backlog-groomer pass 9]
      TERRITORY: `services/geometry/src/geometry/kernel/` STEP export path
      (assembly writer). agentType: kernel-architect.

- [x] (P1, XS) **STEPNAME-1B — the web builds the assembly evaluate request
      without the instance `name`, so every user-facing STEP export falls
      back to the UUID.** DONE 2026-08-29 (frontend-builder). One line —
      `name: instance.name` — and the evidence that it means something.
      **Asserted on the exported bytes, never on a 2xx**:
      `apps/web/e2e/assembly-step-names.spec.ts` builds a part named
      `Flänsch`, instances it twice through the real UI, clicks the real STEP
      cell, and parses the part-21 text with the same `_LITERAL` rule the
      kernel suite uses (both escapes undone, then UTF-8 decoded — a
      substring check would have passed on the mojibake `6c52d5f` fixed).
      Occurrences read `["Flänsch <1>", "Flänsch <2>"]`, the part gets ONE
      shared `PRODUCT('Flänsch')`, and NO name in the file matches a UUID.
      **Mutation evidence**: with the line reverted the same spec reports
      `["9ed8bc86-…", "1a8c2497-…"]` — the audit's exact symptom, reproduced
      — and the unit case reddens to `[undefined, undefined]`. The name is
      sent VERBATIM (`"<part> <n>"`): the writer's contract puts the whole
      name on the NAUO and the suffix-stripped form on the shared PRODUCT,
      so pre-stripping client-side would have split one part into N
      PRODUCTs. Acceptance's last clause checked: `buildEvaluateAssemblyRequest`
      is the web's ONLY evaluate-request builder, so interference is fixed by
      the same line (it ignores the field), and the assembly drawing path
      builds no such request at all — it goes through documents, which has
      always sent the name. Gates: `just lint` exit 0, `pnpm -r typecheck`,
      `pnpm -r test` (2130 + 141), 13/13 assembly + export e2e green on an
      isolated native stack. This is STEPNAME-1's ACTUAL headline
      cause, isolated by the kernel-architect on 2026-08-29 after measuring
      that the geometry writer has carried names correctly since `0d3ea59`.
      `apps/web/src/assembly/evaluateRequest.ts`'s
      `buildEvaluateAssemblyRequest` maps each instance to
      `{instance_id, part_key, grounded, placement, features, materials}` and
      omits `name`, which `EvaluatedInstance` has had (optional, defaulting
      to `None`) since the naming work landed. `services/documents` DOES send
      it (`assemblies.py` `build_evaluate_assembly_request`, `name=
      instance.name`), which is why the defect is invisible from the backend
      and why the audit — exporting through the app — saw UUIDs.
      **Watch the class, not just the line:** an optional DTO field the
      producer silently omits is the same shape as the `extra="ignore"` typo
      trap in CLAUDE.md — everything validates, evaluates and returns 2xx
      while meaning nothing. ACCEPTANCE: `name: instance.name` threaded
      through; a test that asserts on the EXPORTED BYTES (or a re-import),
      never on a 2xx — `services/geometry/tests/test_step_names.py` has the
      part-21 literal parser to borrow, including the two escapes a naive
      `[^']*` gets wrong; the audit's two-part assembly exports with both
      components named. Check the drawings/interference callers for the same
      omission while you are there.
      [src: STEPNAME-1, kernel-architect, 2026-08-29]
      TERRITORY: `apps/web/src/assembly/evaluateRequest.ts` + its unit test.
      agentType: frontend-builder.

- [x] (P2, S) **STEPNAME-2 — CLOSED (kernel-architect, 2026-09-04). Option (a):
      the single-body export now writes through the SAME owned writer as the
      assembly path, and unifying cost nothing a consumer can see.** The
      defect, measured on the bytes for a part named "Flänsch 40°":
      `PRODUCT('FlÃ\x83Â¤nsch 40Ã\x82Â°')` and
      `FILE_NAME(...,'build123d','Unknown')` — the SAME two defects STEPNAME-1
      fixed for the assembly, on the export a user reaches by downloading one
      part, i.e. the common path was the broken one.
      **THE DECISION, since this ticket was mostly a decision.** The worry that
      made (a) a judgement call was that owning the writer would drag XCAF
      assembly structure into a file with none, changing the emitted shape for
      every user and moving every digest. **It does not** —
      `_single_body_xde_document` rebuilds the document build123d's
      `_create_xde` builds for a shape with no children (`makeAssembly=False`,
      auto-naming ON) and the payload is BYTE-IDENTICAL to build123d's for a
      named solid (15 348 B), an unnamed solid (15 335) and a multi-body
      `Compound` named (29 169) / unnamed (29 193). The complete before/after
      diff of the shipped fix is the originating-system field plus, for a
      non-ASCII name, the `PRODUCT` id/name — nothing else. **No golden's
      content hash moves**: the sheet-metal `content_hash` values are sha256 of
      `FlatPattern.to_json_bytes()`, and nothing in the suite pins a digest over
      single-body STEP bytes (checked, not assumed).
      **Mutation evidence, four mutants, all restored:** encoding reverted ->
      8 red (all and only the non-ASCII names x both `BodyShape` members; the
      three ASCII-punctuation shapes stay green, as part 21 always handled
      them); whole path back to `build123d.export_step` -> 10; the
      "unnamed keeps OCCT's default" skip dropped -> 1; and the negative control
      for the structural claim, `makeAssembly=True` -> 12, including the
      byte-determinism gate, because turning a part into an assembly
      reintroduces STEPDET-1's process-global counter. Only the MULTI-BODY cases
      fail under that control — the same blind spot STEPDET-1 paid for.
      Also: the export no longer mutates the caller's shape (it used to borrow
      `shape.label`). Filed from the measurement: STEPHDR-1 (P3).
      [src: STEPNAME-1, kernel-architect, 2026-08-29; closed 2026-09-04]
      TERRITORY: `services/geometry/src/geometry/kernel/export.py`
      (`export_step_bytes`). agentType: kernel-architect.

- [ ] (P3, XS) **STEPHDR-1 — a non-ASCII document name reaches the part-21
      HEADER as raw UTF-8 rather than the standard's `\X2\` escapes.** kind:
      defect. `FILE_NAME`'s NAME field is set through
      `TCollection_HAsciiString`, which is byte-transparent, so
      `export_step_bytes(..., name="括号 A")` writes the raw UTF-8 bytes into a
      header ISO-10303-21 defines over ISO-8859-1. Measured 2026-09-04
      (STEPNAME-2): it round-trips byte-exactly under a UTF-8 decode, and every
      reader we have tried is UTF-8-tolerant, but a strict reader would show
      mojibake. **P3 for two reasons, both worth keeping in the record.** (a) It
      is IDENTICAL in the part and assembly paths — `_write_step_document` is
      the single call site — so this is not a re-creation of the part/assembly
      split STEPNAME-2 closed, and fixing it fixes both at once. (b) The header
      NAME is provenance metadata; the field a downstream tool actually keys on
      is `PRODUCT`, which is correct in both paths as of STEPNAME-2. ACCEPTANCE:
      encode the header name per part 21 (`\X2\<utf-16be hex>\X0\`) and assert
      on the emitted bytes that a strict ISO-8859-1 read recovers the name, for
      the same seven mangling shapes the two naming suites already share. Watch
      the ASCII case stays byte-identical, or every existing digest moves for a
      name that needed no escaping.
      [src: STEPNAME-2, kernel-architect, 2026-09-04]
      TERRITORY: `services/geometry/src/geometry/kernel/export.py`
      (`_write_step_document`). agentType: kernel-architect.

- [x] (P1, S) **STEPDET-1 — CLOSED (kernel-architect, 2026-08-29). The
      canonicalisation is one pattern and a shared helper; the fixture that
      makes the gates able to fail is the deliverable.** `_canonicalise_occurrence_ids` is now
      `_canonicalise_writer_counters` and renumbers BOTH process-global
      counters through one shared `_renumber_in_appearance_order` — an
      extension, not a second parallel mechanism.
      `goldens-assembly/assembly-two-multibody-brackets` is the bolted golden
      verbatim (same instances, mates and seed) plus one disjoint 10 mm cube
      per part, so the joint's reviewed analytic answer carries over and
      multi-body is the only new variable; hand-derived, measured deviations
      volume **0.0**, area 1.8e-12, centroid <= 1.1e-09, solved z 1.18e-08
      against a documented 1e-6. It is ASSERTED to reach the `Compound` path
      (2 translator PRODUCTs, 2 B-reps for 1 unique part, 4 NAUOs for 2
      instances) rather than assumed. **Mutation:** reverting the
      canonicalisation reddens 4 cases (both determinism gates on the new
      golden, its counter-pinned byte assertion, the naming suite's
      in-process one) while 54 pass — including every determinism case of
      both older goldens in all four formats, which is the blind spot
      measured. `At index 4024 diff: b'1' != b'2'`. Two neighbouring gates
      carried the same "one part is one solid" assumption and rejected the
      new golden (`2 B-reps written for 1 unique part(s)`); both are now
      per-BODY. The recorded live limit in `test_step_names.py` is deleted
      and replaced by its positive form. No golden's content hash moves: a
      FIRST export in a process was already counter-1, so the fix changes
      only the repeat export (verified legacy-vs-new byte comparison, all
      three goldens). Gates: full geometry suite green, `just lint` 0,
      pyright clean; no DTO touched. STEPNAME-2 is unaffected — measured, the
      single-body path builds no XCAF assembly and is already byte-stable.
      Original entry follows.
      kind: defect (determinism, RESEARCH §9). Found by
      STEPNAME-1 (2026-08-29) while writing a determinism assertion for its
      own change — the assertion failed, and not for the reason expected.
      When a component's body is a `Compound` (i.e. a multi-body part, MB-0,
      an ordinary thing to instance), OCCT wraps it in an extra unnamed
      assembly level and names that level's PRODUCT `'Open CASCADE STEP
      translator 7.9 N.M.K'`, where **N is a process-global write counter**.
      Two exports of the same assembly in one worker differ — measured, first
      difference at byte 3462, `1.1.1` vs `2.1.1`. Reproduced deterministically
      by `test_a_multi_body_part_makes_the_export_non_deterministic`, which
      asserts in the FAILING direction so closing the gap reddens the suite.
      **Why nothing caught it:** it is exactly the defect
      `_canonicalise_occurrence_ids` already fixes for the NAUO id, in a
      second byte range nobody looked at, and BOTH shipped assembly goldens
      are made of single `Solid` parts, so the extra level never appears in
      them. `test_assembly_export`'s in-process AND interpreter-restart
      determinism gates therefore pass while the property is false — the
      archetypal gate that cannot fail for the reason you care about, and the
      reason the fix needs a GOLDEN, not only a canonicaliser. Impact: a
      worker re-exporting an unchanged assembly returns different bytes, so
      any content-addressing over the artefact misses. ACCEPTANCE (all met): a
      multi-body assembly golden lands FIRST and is shown to fail the existing
      in-process + restart determinism gates (the negative control); the
      counter is then canonicalised the same way the NAUO id is; both gates go
      green on it; the recorded live limit in `test_step_names.py` is DELETED
      in the same commit and the deletion is stated in the message.
      [src: STEPNAME-1, kernel-architect, 2026-08-29]
      TERRITORY: `services/geometry/src/geometry/kernel/export.py`
      (`_canonicalise_occurrence_ids` and its neighbours),
      `services/geometry/goldens-assembly/`,
      `services/geometry/tests/test_assembly_export.py`,
      `services/geometry/tests/test_step_names.py`. agentType:
      kernel-architect.

**SIGNIN-1 is SHIPPED (`bf65ddc`) — see Done archive for evidence/gates.**

- [ ] (P2/P3, S) **SM-POLISH-1 — remaining sheet-metal/assembly polish from
      the fabrication-handoff audit, bucketed rather than individually
      ticketed to keep the board a workable size.** Each is small,
      independently shippable, and cited by finding id in
      `docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" — pull
      the one you're building and re-derive acceptance from the finding
      text before starting: **P2** — continue the rebuild past a failed
      feature for features that don't depend on it (S-24); four
      orientation view-bar buttons share one icon, byte-identical SVGs
      (S-30); flange-length/hem-return has no stated datum (S-8/S-12);
      sketch dimensions render as bare numerals with no extension
      lines/arrowheads (S-35); per-instance appearance + non-interpenetrating
      seed placement in assemblies (S-16); auto-layout should fill the
      sheet at the largest fitting scale and suppress trailing zeros
      (S-28); Measure needs diameter/radius/centre-to-centre (S-33); STEP
      import at 12.1 s for an 18-face part is the one performance outlier
      (S-37 area). **P3** — export the full title string, not a UI-
      truncated ellipsis (S-14); sheet-metal recognition on an imported
      solid (S-37); contact shadow + edge overlay on shaded solids, and
      drop the decorative empty rows on an empty register (S-33/S-2);
      opening a newly created assembly should navigate into it, matching
      part-create (S-17).
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)",
      filed as a bucket by backlog-groomer pass 9]
      **ADDED, groom pass 11 (2026-08-24), same bucket shape — pull by id,
      re-derive acceptance from the finding:** **P1** — after a failed
      rebuild, fit the view and clamp/hide pick proxies that render off
      the visible frame (T-9: three of four repair-mode edge proxies
      measured at y=-186, y=1017, x=-4 on a 1000px-tall window; the camera
      is also left at the sketch-edit orientation rather than refit).
      **P2** — Measure's circle-to-circle reading is not centre-to-centre
      and doesn't say what it measured (T-14, corroborates S-33: two
      Ø6.6 holes 47mm apart in both axes read `DISTANCE 70.9597mm`, which
      is neither the 47mm nor the 66.468mm diagonal); drawing dimensions
      have no tolerance field at all and print trailing zeros (`Ø25.000`)
      — T-17, corroborates/extends S-35; no centre marks, centrelines, or
      hole table on drawing views (T-17); orientation-button glyphs are
      still only a 1.4px dot apart at 24px render size — T-19 corroborates
      S-30, "half closed" (a per-facet dot now exists, still illegible).
      **P3** — creating a DRAWING also fails to open it (T-25 extends
      S-17's assembly finding to a third creation flow — three flows, two
      behaviours); duplicate `Centroid`/`Centre of mass` rows carrying the
      same number, no inertia tensor, and stray tooltips left painted in
      the viewport after the cursor moved (T-24).
      [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-24" fourth/fifth passes
      T-9/T-14/T-17/T-19/T-24/T-25, added by backlog-groomer pass 11]
      TERRITORY: varies per item — see the cited finding. agentType: varies
      (mostly frontend-builder; S-37's import recognition is
      kernel-architect).

- [ ] (P2, S) **GQA-1 — the invariant triple tier 4a compares (outer area,
      perimeter, in-plane centroid) is NOT a fingerprint of the outer wire;
      §12b overclaims "the same outer wire, to tolerance."** kind: defect
      (a design-doc overclaim plus a real, if narrow, resolver gap — NOT a
      regression of `1e39c14`/GEOM-3: tier 4b admits the same wrong face
      identically, so this predates GEOM-3 and GEOM-3 neither introduced nor
      closed it). All three invariants are exactly preserved under any rigid
      ROTATION of the wire about its own centroid, so two congruent-but-
      differently-oriented faces sharing an in-plane centroid agree on all
      three and tier 4a wrongly admits either for the other. MEASURED
      (`docs/GEOMETRY-QA.md`, 2026-08-16 GEOM-3 independent verification): a
      100x40/40x100 transition-bracket flange pair, both `A=4000.000
      P=280.000 C=(0,0)`, resolves to the WRONG face — `resolve_face_plane ->
      origin (0.0, 0.0, 10.0)`, a **40.000 mm silent error** at the resolver
      level. Severity kept at P2 not P0: three independent attempts to build
      a feature-tree vehicle that reaches this from an ordinary edit all hit
      real kernel guards (`cut_removed_nothing`, `boolean_failed`,
      `subshape_ambiguous`) — resolver-level reachability is proven,
      product-level reachability is not. FIX: (a) correct §12b's prose from
      "narrows congruent to the same outer wire" to "the same outer area,
      perimeter and in-plane centroid" and add the rotation/reflection
      family to the honest-limits list; (b) the durable close needs an
      orientation-bearing invariant (the three scalars gated today are
      deliberately not one) — a second area moment or an anchored boundary
      hash, TBD by whoever picks this up. ACCEPTANCE: §12b's sentence
      corrected; either a new invariant closes the transition-bracket case
      (new golden) or the honest-limit is formally documented with a gated
      characterization test if closing it is deferred again. Mutation check:
      `test_faces_geom3_qa.py::test_the_outer_invariant_TRIPLE_is_NOT_a_
      fingerprint_of_the_outer_wire` already gates the KNOWN-limit
      characterization — goes red the day a shape-sensitive invariant is
      added, which is the acceptance signal for a real fix.
      [src: geometry-qa independent verification of GEOM-3, `0628ceb`,
      2026-08-16, docs/GEOMETRY-QA.md "GQA-1"]
      TERRITORY: `docs/design/topological-naming.md` §12b (doc fix, cheap,
      do first), `packages/py-kit` (`PlanarFaceSignature`, if a new
      invariant is added), `services/geometry/src/geometry/kernel/faces.py`
      (tier 4a/4b), geometry goldens. agentType: kernel-architect.

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

- [x] (P1, M) **FOUNDER — no Fusion-style hover-a-face-to-sketch.** DONE —
      rest the pointer on a face with nothing armed and the viewport writes a
      drafting LEADER NOTE (anchor dot + hairline stub + a `Sketch ↵` chip);
      click it or press Enter and a sketch opens on that face. It calls the
      SAME `handleNewSketch` + `authorFacePlane(face)` pair the toolbar flow
      calls — proven byte-identical at the wire by a new e2e case that records
      the `on_face` datum POST from BOTH paths for one face and compares them
      (ablation: perturbing the centroid by 1 mm reports `"z":10` vs `"z":11`).
      UX decided by the builder, per the item: the note is written on REST
      (`proposal.dwellMs` 320 ms) not on hover, so sweeping the model proposes
      nothing; the face's own SEL-1 tint carries the proposal and the chip only
      confirms it; and once written it LATCHES — travelling onto the chip takes
      the pointer off the mesh, and the first build withdrew the note in the
      instant the user reached for it. Keyboard: `Enter` accepts the showing
      note (declared in `shortcuts/registry.ts`, printed on the chip, on the
      key sheet); tabbing to named faces stays the Sketch command's job.
      Reachability measured, not assumed — `elementFromPoint` at the chip's
      centre resolves to the chip, and removing its `pointer-events` reports
      `"viewport"`. Founder shots: `docs/screenshots/hover-sketch-{before,
      after}-{1280x800,1600x1000}.png`, pixel-aligned pairs.
      ORIGINAL REPORT, for the record:
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
      agentType: frontend-builder. **Founder reports outrank everything —
      this is next up in `apps/web/src/viewport/**` once PICK-2/FB-21/FB-9/
      SEL-8 clear that territory this batch (contention, not demotion).**

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

**K2 is CLOSED (2026-08-29, backend-builder) — route-auth posture gate landed
after four audit passes asking for it (J7 -> K2 -> L3 -> M3); posture was
already correct, no route changed.** Current measurement: gateway **89/84/5**,
documents **64/60/4**, geometry **28 identity-free**. Floors kept at 88/64/28
DELIBERATELY (the count the gate must exceed, not a stale reading — one route
has been added since Pass 7 M3 measured 88) plus an `unwalked` cross-check
against each app's own OpenAPI schema. Walker uses
`fastapi.routing.iter_route_contexts`, not hand-recursion — the latter gets
the right count with wrong paths/dependencies on nested/include-level auth,
a false-positive risk on a security gate documented in CLAUDE.md. 13 tests,
controls proven (naive walk refused at `3 < 88` after passing the posture
check alone). See Done archive / `docs/CHANGELOG.md` "K2 CLOSED" for full
detail. [src: engineering-auditor pass 5, 2026-08-14 (K2); was J7, 2026-07-30]

**PBT-1 is CLOSED (2026-08-29, kernel-architect) — the randomised sweep that
found SETTLE-2/3 is committed as a seeded fixed corpus** (2000 trials, `seed
20260822`, +10.3s/0.9% of the pytest job), and its alarming 7-of-155
violated-constraint headline is re-measured at 0-of-1328 (post SOLVE-CRASH-1).
Argued against `hypothesis` (reproducibility from the commit alone, since
only the orchestrator can read CI). Mutation-checked against both root
causes it was built from. Three NEW findings reported rather than fixed —
SOLVE-CRASH-1 (closed, above), SOLVE-CONFLICT-MOVED-1, and
SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (both still open, below). See Done archive
/ `docs/CHANGELOG.md` "PBT-1 CLOSED" for the full argument.
[src: docs/AUDIT-ENGINEERING.md "Pass 9" N2, filed by backlog-groomer pass 11]

**SETTLE-BENCH-1 RENAMED/ELEVATED -> SETTLE-PERF-1 (P1->P0), groom pass
12.** Uncommitted engineering-audit Pass 10 turned the "documented n^3
worst case" into a live measurement (1,560x at 48 lines, 230s at 96 —
DoS-shaped against the gateway's 90s no-cancel timeout). Full ticket moved
to the Ready section, top of queue.

- [ ] (P2, XS) **CONTRACT-1 — `SolvedDimension.value_mm`'s OpenAPI
      docstring still describes pre-SOLVE-1 semantics, and `gen-check`
      cannot see it because it regenerates from the same wrong docstring.**
      kind: defect (contract/documentation drift a client relies on).
      MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 9" N3): SOLVE-1's
      `_dimension_readouts` now reports the MEASURED value whenever it
      disagrees with the requested one by more than `SATISFIED_TOL_MM`, but
      the pydantic docstring (`packages/py-kit/src/py_kit/schemas/
      sketch.py:575-605`) and both committed OpenAPI docs still say
      `value_mm` is "the evaluated literal/expression value that was fed to
      the solver" — i.e. the opposite of what SOLVE-1 does in exactly the
      case it exists to handle, with no field distinguishing requested-vs-
      measured. FIX: correct the docstring in two sentences; consider an
      explicit `verified`/`measured: bool` field so the substitution is
      disclosed in the payload rather than inferred from a sibling
      (`status`) on a different object. ACCEPTANCE: `just gen` regenerates
      contracts with the corrected description; `packages/ts-client`
      reflects it.
      [src: docs/AUDIT-ENGINEERING.md "Pass 9" N3, filed by backlog-groomer
      pass 11]
      TERRITORY: `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType:
      kernel-architect (schema owner) or backend-builder.

- [ ] (P2, S) **SEC-TEST-1 — no negative control proves the gateway
      ignores a client-supplied principal header.** kind: capability (test
      gap on a correct-today, refactor-fragile control). MEASURED (`docs/
      AUDIT-ENGINEERING.md` "Pass 9" N6): `upstream.py:186-189` builds the
      forwarded header set explicitly rather than proxying, and the only
      caller adding a principal is `parts.py:88` — so a forged
      `X-Loft-Principal` cannot reach `documents` today, but this is
      correct BY CONSTRUCTION, one plausible refactor ("forward the
      client's other headers through") away from being wrong, with
      cross-tenant impersonation as the failure mode, and
      `grep -rn "spoof\|impersonat\|forged" services/gateway/tests` finds
      only JWT-forgery tests. FIX: two request-level tests — a
      client-supplied `X-Loft-Principal` is dropped/ignored, and the
      upstream header always equals the authenticated token's subject
      (the second half already exists in `test_assemblies_proxy.py:275`).
      ACCEPTANCE: both tests pass today and fail under a mutation that
      merges client headers into the upstream set.
      [src: docs/AUDIT-ENGINEERING.md "Pass 9" N6, filed by backlog-groomer
      pass 11]
      TERRITORY: `services/gateway/tests/test_upstream.py` or similar
      (new). agentType: backend-builder.

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

- [ ] (P3, S) **CI-4 — standing umbrella for e2e-suite instability under
      runner load. ORIGINAL QUESTION ANSWERED 2026-08-29 (qa-tester, eleven
      full-shard + 17 targeted runs): NO, the suite is not systemically
      unstable — shard 3/4 was structurally overloaded (Playwright cuts
      whole files in filesystem order on equal test COUNT, and the
      heaviest specs share alphabetically-adjacent prefixes), measured at
      1.58x the median wall.** Downgraded P2->P3 this pass: every diagnosed
      cause is now closed (CI-5, CI-5a, QA-SEL6-ORTHO-1, the shard-4/4 hem
      spec, QA-CI4-HEADROOM-1) and the imbalance itself is fixed (CI-BAL,
      below, duration-aware sharding, verified on the real CI runner at
      1.16x spread). **REMAINING under this umbrella: QA-CI4-MATE-1 alone**
      (a mate-axis reachability scan measured zero addressable pixels once
      under CPU load, in 1 of 6 runs — filed as its own ticket, unreproduced
      hypothesis, do not "fix" by re-running until green). Kept open as a
      standing umbrella for the next unexplained shard-3/4 red, not as an
      active fire. Full incident history (the original three-mechanism
      diagnosis, the substrate pass, the four separately-fixed causes): see
      `docs/CHANGELOG.md`'s CI-4 sections and this Done archive.
      [src: orchestrator CI root-cause, 2026-08-11; qa-tester CI-4 pass,
      2026-08-29]

**CI-BAL is CLOSED (2026-08-29, platform-builder) — the e2e shard split is
duration-aware (`scripts/e2e-shard-plan.py`, `scripts/e2e-durations.json`,
longest-processing-time packing over measured per-file duration), and the
two cheaper alternatives (splitting the heavy spec files; more workers /
`fullyParallel`) were ruled out by measurement, not taste.**
**VERIFIED ON THE REAL CI RUNNER, groom pass 19 (corrects the local-box
figure this ticket originally shipped with): per-shard walls 1425/1337/1550/
1360s, a 1.16x spread (down from 1.58x), 25.8 min critical path, step-cap
headroom 1.55x (not the 2.1x first computed from a local-box run — the
duration manifest was measured on this container and CI's relative per-file
costs differ). Follow-up: SHARD-MANIFEST-CI-1 (P3, below) — seed the
manifest from CI's own reports.** Local-box validation (kept for the
GATE-1 coverage proof, which does not depend on absolute timings): a real
four-shard run measured 1132/1085/1138/1116s, 686/686 expected, 0 flaky, a
1.05x spread; GATE-1 (an unmeasured file is still assigned, weighted
heaviest) proven live with a throwaway spec; `--drift`'s destructive-advice
footgun on a partial report set found and closed (`--allow-shrink`).
[src: platform-builder, 2026-08-29; measurement in docs/QA-REVIEW.md CI-4]

**CI-5 is CLOSED (`2874f0a`, 2026-08-28, orchestrator) — a red e2e shard's
failure list was unreachable from the orchestrator's only channel (job-log
tails of 60/190/255 lines all failed to reach it past service-log/upload
chatter). Every run now ends with a compact verdict block naming each
failure, guarded against silence (`::error::` + exit 3) and cross-checked
against the report's own stats. See Done archive.**

**CI-5a is CLOSED (`ecc1fb7`, 2026-08-28, orchestrator) — the verdict block
was miscounting a declared `test.fail()` case as a real failure (classified
from `results[].status` instead of Playwright's reconciled `tests[].status`);
its own cross-check is what caught it. The inversion (a declared-fail that
PASSES) is now named too, as `XPASS … [annotation NO LONGER HOLDS]`. See Done
archive.**

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
      **CORROBORATED, groom pass 11 (2026-08-24, T-23): a full DOM sweep for
      `[data-testid*="handle|gizmo|drag|arrow|manip"]` returns `[]` — the
      mandate's own named "biggest gap," M5, is still at exactly zero, not
      partially shipped. Extrude is a numeric field with a live coloured
      preview and no draggable arrow; nothing proposes the next verb after a
      solved sketch beyond pre-selecting the profile.** [src: docs/
      AUDIT-PRODUCT.md "Pass 2026-08-24 (fifth pass)" T-23]
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
    - [x] (c1) **web — the setup band drafts an ASSEMBLY — SHIPPED 2026-08-27**
          (frontend-builder, REACH-ASMDRAW): `drawing-part-select` widened from a
          part picker to a grouped SOURCE picker over parts AND assemblies
          (`drawing/source.ts`; `SelectField` learned `optgroup`), testid kept so
          the twenty existing drawings specs stay green. `AssemblyPage` gains the
          band `Drawing` action → creates the drawing and opens it at
          `?source=<assembly>`, pre-selected. Compose gates on the source KIND
          (an assembly sheet has no client feature tree and needs none); flat
          pattern + section disable with the reason, keyboard path guarded. The
          Views panel now counts PLACED edges when there is no client evaluate —
          it read "0 edges" over a full assembly sheet. E2e
          `assembly-drawing.spec.ts` (real HLR ink asserted, 1280 band fit).
          Deferred: assembly fit-scale (needs the solved compound's extents).
    - [x] (c2) **web — the sheet's numbered PARTS LIST — SHIPPED 2026-08-27**
          (frontend-builder, REACH-ASMDRAW): `GET /drawings/{id}/bom` gets its
          first caller in 13 months of existing (`fetchDrawingBom`). A Parts list
          block sits beside Notes: balloon item numbers (a circled numeral — the
          drafting artifact, and the number is content, not decoration), qty,
          current names, each row opening the document it names; a `missing: true`
          line keeps its number and reads "Deleted document". On a PART-sourced
          sheet the block is PRESENT but disabled, carrying
          `drawing_bom_source_not_assembly` as a readable sentence that is
          FOCUSABLE — reachable by Tab, not hover-only. E2e
          `drawing-parts-list.spec.ts` (item 1 qty 2 / item 2 qty 1 by name,
          numbers survive a reload, row navigates, reason read via Tab).
          `check-ui-parity.py` UNCALLED OPERATIONS 3 -> 2 (82/85 -> 83/85).
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
- [x] (P2, S) **Promote the durable EDGE tier into `geometry.kernel.edges`.**
      DONE 2026-08-24 (`c2700ee`, folded into NAME-2's closure): `resolve_edge_durable()`
      now lives in `geometry.kernel.edges`; fillet/chamfer and sheet-metal edge
      flange/hem pick it up via `select_edges`/`_fold_flange_off_edge`.
      [src: topological-naming §11]
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

- [ ] (P3, S) **QA-CI4-MATE-1 — a mate axis measured ZERO addressable pixels
      under CPU load, and it is the one of three shard-3/4 reds that is NOT
      root-caused.** kind: defect (e2e, possibly app). Found by the CI-4 QA
      pass (2026-08-29, `docs/QA-REVIEW.md`) while reproducing shard 3/4:
      `pick-affordance.spec.ts:1680` ("assembly mates: each INSTANCE's own
      geometry is the mate target") failed in 1 of 6 full shard runs, only
      under two CPU spinners, with `mate axes addressable >= 40px along:
      #13 0px #14 28px` — axis #13 not SHORT but ABSENT, while its sibling
      #14 measured 28 px. 0 of 5 other runs. The leading hypothesis is that
      the overlay or the camera had not settled when the reachability scan
      ran, which is the same family as the two defects the pass DID close,
      but it is a hypothesis and is filed as such rather than patched.
      FIX: instrument first — record the mate-axis overlay's own settle
      state and the camera pose at scan time, reproduce under load, and only
      then decide whether the scan or the app is at fault. ACCEPTANCE: the
      cause is named with a measurement, and whichever side is wrong is
      fixed with a control that fails when the fix is reverted. DO NOT
      "fix" by re-running until green or by dropping the 40 px floor.
      [src: qa-tester CI-4 pass, 2026-08-29]

- [x] (P2, S) **QA-CI4-HEADROOM-1 CLOSED — both tests were ALREADY failing,
      the work was cut before the ceiling was raised, and my first theory
      about the cost was wrong.** kind: defect (e2e). Filed and closed by the
      CI-4 QA pass (2026-08-29); full write-up in `docs/QA-REVIEW.md`.
      The in-shard headroom table understated it: run ALONE,
      `qa-sketch-frame:478` timed out in 1 of 3 QUIET isolated runs and 3 of
      3 under two CPU spinners, and `qa-sel4-verify:503` failed 3 of 3 under
      load — every one as a bare "Test timeout of 60000ms exceeded" naming
      none of the 54 clicks it might have died in. NOT the
      `expectSeatsSettled` mechanism (a fixed frame count whose wall time
      scales), and NOT the one I guessed either: I found the ring scan doing
      1068 full-frame canvas readbacks, batched them 356:1, and the wall
      clock did not move. Phase timers then showed the truth — the ZOOM LOOP
      was 47 % of the test (15.8 s of 33.2 s) and the scan I had optimised
      was 0.6 % (190 ms), because the loop re-parked the pointer with a
      `mouse.move` before each of 48 wheel notches when the cursor was
      already there. FIXED in this order: work cut (one park per leg; one
      readback per scan; `qa-sel4-verify:382`'s hand-rolled 8 px halo now
      calls `clearOfSilhouette` — its second real use), then ceilings raised
      to 180 s from the measured distribution. After: `:478` 36.6-39.0 s
      quiet (4/4) and 49.7-57.5 s loaded (7/7); `:503` 52.1-53.8 s quiet
      (4/4) and **66 s** loaded (3/3) — a 10 % overshoot of the old 60 s,
      which is why it could never pass under load. Its 504 sequential
      pointer moves cannot be batched: the browser must hit-test each
      position and the hit test IS the measurement. No assertion weakened.
      Verified on a full shard 3/4 under two spinners: 171/171 expected, 0
      unexpected, `load1` median 10.31 on 4 cores (~2.6x oversubscription,
      heavier than the 1.5x this ticket's acceptance named).
      **THE ACCEPTANCE CRITERION AS WRITTEN IS NOT MET, and this is closed on
      the two tests it NAMED, not on that.** "No shard-3/4 test under 3x its
      ceiling at 1.5x oversubscription" was over-broad for a ticket about two
      specs: the two are now 3.1-3.6x and 2.7x, but `pick-affordance:911`,
      `qa-reach-batch:298` and `qa-sel4-verify:382` were ~2.0x before this pass
      and still are, and at 2.6x load the worst is `pick-affordance:926` at
      1.4x. A shard-wide floor is a larger piece of work — most of the
      remainder are census tests whose cost IS their assertion — and it wants
      its own ticket rather than being smuggled in here. Filed as
      QA-CI4-HEADROOM-2 below.
      One side-finding worth keeping: batching the scan removed an
      ACCIDENTAL settle (356 sequential awaits were letting the canvas
      repaint after a DOM-only wait), which failed once as "the origin ring
      must be visible ink"; fixed by stating the wait with `waitForFrames`
      rather than by un-batching. RESIDUE, not re-filed as a defect:
      `:478` is 49.7-57.5 s of REAL work under load, so a runner 3x slower
      than this box approaches 180 s again. The durable fix is fewer zoom
      legs or fewer notches, and both weaken a claim the test exists to
      make — a product-QA trade for the spec's owner, not a timeout tweak.
      [src: qa-tester CI-4 pass, 2026-08-29]

- [ ] (P3, M) **QA-CI4-HEADROOM-2 — shard 3/4 still has ~6 tests at ~2x their
      own timeout, and each needs the same one-at-a-time treatment.** kind:
      defect (e2e). Split out of QA-CI4-HEADROOM-1 (2026-08-29) rather than
      left as an unmet acceptance line on a closed ticket. That ticket named
      two tests and fixed them; the blanket floor it also asked for — no
      shard-3/4 test under 3x its ceiling at 1.5x CPU oversubscription — is
      NOT met and was over-broad for its scope. Measured at 1.5x:
      `pick-affordance:911` 2.0x, `qa-sel4-verify:382` 2.0x,
      `qa-reach-batch:298` 2.1x. At 2.6x oversubscription the worst is
      `pick-affordance:926` at 1.4x (43.3 s against the default 60 s). These
      are mostly CENSUS tests whose cost IS their assertion — hundreds of
      sequential pointer moves the browser must hit-test one at a time — so
      the readback batching that helped elsewhere does not apply, and the
      honest lever per test is either fewer sample points (weakens the claim,
      needs an owner's call) or a ceiling set from a measured distribution.
      FIX: work one test at a time, cutting redundant round trips first and
      raising the ceiling second, with the numbers written beside each — the
      pattern in `qa-sketch-frame:478`. DO NOT do a blanket sweep of
      `test.setTimeout` values: a ceiling nobody measured is what produced
      this ticket. ACCEPTANCE: every shard-3/4 test at >=3x its ceiling under
      1.5x oversubscription, with the census attached; any test that cannot
      reach it says why in its own comment. [src: qa-tester, 2026-08-29]

## Later (P3)

**Filed groom pass 27 (2026-09-23) — small, independently-shippable cleanup
found while reconciling `f9fcce6`/`bc53e7d`:**

- [ ] (P3, XS) **DATUM-DEADCODE-1 — `canSubmitOffset` in
      `apps/web/src/features/datum.ts` is used only by its own test.**
      kind: cleanup (dead code). `17763b5` (groom pass 27) moved
      `OffsetPlanePanel` onto `datumSubmitBlocker` directly; `canSubmitOffset`
      is now referenced only from `datum.test.ts`. ACCEPTANCE: delete the
      function and its test cases (or fold the equivalent assertion into a
      `datumSubmitBlocker` test if the coverage is otherwise lost); `grep -rn
      canSubmitOffset apps/web/src` finds nothing outside the deletion diff.
      [src: found while reconciling `17763b5`, filed by backlog-groomer
      pass 27] TERRITORY: `apps/web/src/features/datum.ts`,
      `apps/web/src/features/datum.test.ts`. agentType: frontend-builder.
- [ ] (P3, XS) **SHORTCUT-SHEET-SKETCH-FIT-1 — the shortcut sheet's View
      group still says view keys don't work while sketching, and does not
      list `0` = Fit sketch.** kind: defect (docs-in-product accuracy).
      `registry.ts`'s View group note reads "Whenever the camera is yours
      (not while sketching)" — false since `f9fcce6` (F-11), which binds
      the SAME `0` key (`FIT_KEY`, read off `VIEW_SHORTCUTS`) to "Fit
      sketch" while a sketch is open; `viewShortcuts()` labels it "Fit to
      the model" unconditionally, which is also wrong in that state.
      ACCEPTANCE: the View group's note and the Fit row's label are correct
      in BOTH contexts (not sketching: "Fit to the model" / the existing
      note; sketching: "Fit sketch" / a note that says the Fit key works
      while sketching, others do not) — derived from state, not hand-kept
      in sync with `sketchFitShown`. [src: found while reconciling
      `f9fcce6`, filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/src/shortcuts/registry.ts`. agentType: frontend-builder.
- [ ] (P3, XS) **NEXTSTEP-COMMENT-STALE-1 — a stale comment and a
      duplicated-label pair in `apps/web/src/components/nextStep.ts`.**
      kind: cleanup (doc/DRY). The module doc says the dot "deliberately
      carries no word, no key chip and no colour of its own" — true when
      written, false since `bc53e7d` (groom pass 27) gave the resting dot a
      NEXT+label+key stamp on hover/focus/once-per-step. Separately,
      `REPEAT_ROWS[].label` (e.g. `"Extrude"`) is a second hardcoded copy of
      the word each `ToolButton` already carries via its own `label` prop in
      `CreateStrip.tsx` — the two can drift (nextStep.ts is used only to
      lower-case it into a caption, e.g. "Another extrude on this body").
      ACCEPTANCE: correct the comment to describe the current behaviour;
      either derive `REPEAT_ROWS[].label` from the same source
      `CreateStrip.tsx` reads (if practical) or, if the two must stay
      separate strings, add a unit test that fails when they disagree so
      the duplication is monitored rather than silent. [src: found while
      reconciling `bc53e7d`, filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/src/components/nextStep.ts`,
      `apps/web/src/components/CreateStrip.tsx`. agentType:
      frontend-builder.
- [ ] (P3, XS) **SCREENSHOT-REFRESH-SKETCH-FIT-1 — founder screenshots for
      sketch-mode specs (`ghost1-*-after.png`) and `next-step-accent-*.png`
      predate `f9fcce6`/earlier sketch-mode changes and are stale.** kind:
      process (screenshot currency). Founder screenshots are refresh-on-
      demand (CLAUDE.md), not regenerated per-run, so they silently drift
      behind the product; the sketch-mode shots now predate the Fit control
      and the current next-step note grammar. ACCEPTANCE: run
      `UPDATE_SCREENSHOTS=1 pnpm --filter @loft/web e2e` for the affected
      specs, review the diffs (this is the one check that asks "is the
      thing legible", per CLAUDE.md), and surface the refreshed before/after
      pair to the founder at the next milestone rather than silently
      committing new PNGs. [src: found while reconciling `f9fcce6`/
      `bc53e7d`, filed by backlog-groomer pass 27] TERRITORY:
      `docs/screenshots/`. agentType: frontend-builder or qa-tester.

**Filed groom pass 25 (2026-09-15):**

- [ ] (P3, S) **AREA-INTEGRATION-1 — surface area has the same fixed-order
      integration bias volume had (F1), and it is deliberately NOT fixed.**
      kind: known limitation (tracked, not silently dropped). MEASURED:
      the adaptive area integrator does NOT converge on the KUKA import —
      it moves from 1.74e-05 to 2.91e-05 between eps 1e-8 and 1e-10, i.e.
      the change is the SIZE of the signal, not noise around a stable
      answer — at ~11s extra cost. Trading a known small bias for an
      unconverged number at double the price is not an improvement, so F1's
      fix (`f7cd483`) deliberately left `measure_shape`'s area path on the
      fixed-order integrator and pinned the decision visibly via the new
      `loft-spline-sections-nurbs-h30` golden. ACCEPTANCE (when someone
      picks this up): either a smarter integration scheme that DOES converge
      on real NURBS surfaces at acceptable cost, or a documented decision to
      leave area on the fixed order permanently with the bias bounded and
      stated. Do not "fix" this by copying volume's `eps=1e-10` verbatim —
      it was measured NOT to help here. [src: geometry-qa gauntlet + F1 fix,
      `docs/GEOMETRY-QA.md`/`f7cd483`, 2026-09-15] TERRITORY:
      `services/geometry/src/geometry/kernel/measure.py`. agentType:
      kernel-architect.

- [ ] (P3, XS) **GEN-CHECK-VERDICT-1 — `gen-check`'s green message doesn't
      mention its third leg.** kind: defect (gate legibility). `153cfa6`
      added a third diff (`packages/loft-script/src/loft/_operations.py`)
      to `scripts/gen-check.sh`, but the success line still reads
      `gen-check: contracts + ts-client match generated output.` — a reader
      cannot tell from the message whether the Python operation table was
      checked at all. ACCEPTANCE: the verdict line names all three legs.
      [src: code review P2-8, `docs/CODE-REVIEW.md`, `451245c`] TERRITORY:
      `scripts/gen-check.sh`. agentType: platform-builder.

- [ ] (P3, M) **DOCS-EXPLORER-1 — decide whether to restore an interactive
      API explorer, and how.** kind: question (product/DX decision).
      `725bc4b` set `docs_url=None`/`redoc_url=None` to fix the air-gap
      claim (Swagger/ReDoc pulled `cdn.jsdelivr.net`/Google Fonts on the
      published port); a contributor hitting `/docs` now gets a bare 404
      with no explanation and QUICKSTART does not mention the explorer at
      all. Three options, in cost order: (a) one QUICKSTART line pointing at
      `/openapi.json` and explaining the explorer is off deliberately
      (cheapest); (b) serve `/docs`/`/redoc` only when `LOFT_ENV=dev` (the
      posture switch already exists, and the air-gap claim is about a
      PUBLISHED gateway, not a developer's laptop); (c) vendor the ~3MB of
      swagger-ui assets so the explorer works fully air-gapped even in
      production (most expensive, most complete). ACCEPTANCE: a decision
      recorded here or in `docs/OPERATIONS.md`, with whichever option
      implemented. [src: code review clean-bill note, `docs/CODE-REVIEW.md`,
      `451245c`; `725bc4b`] TERRITORY: `docs/QUICKSTART.md`, `packages/py-kit`
      (if (b) or (c)). agentType: platform-builder / founder decision.

- [ ] (P3, S) **SHARD-MANIFEST-CI-1 — the e2e duration manifest
      (`scripts/e2e-durations.json`) was measured on this local container,
      and CI's relative per-file costs differ enough to move the answer.**
      kind: capability (process/tooling accuracy). Found by the orchestrator,
      groom pass 19, while verifying CI-BAL's headroom claim on a real CI
      run: the local-box manifest predicted a 1.05x shard spread and 2.1x
      step-cap headroom; the real GitHub Actions runner measured a 1.16x
      spread and 1.55x headroom — still a large improvement over the
      count-based cut's 1.58x, but a materially different number from what
      was shipped, because per-file cost RATIOS (not just absolute walls)
      shift between this container and the runner. FIX: seed
      `e2e-durations.json` from CI's own uploaded JSON reports (the
      `e2e-shard-plan.py --emit-durations` path already exists locally;
      extend it, or a new workflow step, to consume `playwright-report`
      artifacts from a recent green `e2e` run instead of a local
      `--self-test`/local measurement). ACCEPTANCE: the manifest's
      provenance note states which run it was derived from; a re-measurement
      on CI shows the shard spread converging closer to 1.00x than the
      current 1.16x, or the ticket records why it does not.
      [src: orchestrator CI-runner verification, filed by backlog-groomer
      pass 19]
      TERRITORY: `scripts/e2e-shard-plan.py`, `scripts/e2e-durations.json`,
      `.github/workflows/e2e.yml`. agentType: platform-builder.

- [ ] (P3, S) **QA-CI4-LINES-1 — a shard verdict's `file:line` is not a
      stable identifier: 45 of 169 specs report a different line between
      runs of byte-identical source.** kind: defect (tooling). Measured by
      the CI-4 QA pass (2026-08-29) across five shard-3/4 runs at the same
      commit: `parts-home.spec.ts`'s "create → list → open → back → delete →
      persists" reports line 18 in four runs and 12 in the fifth; ten of
      shard 3/4's 25 files are affected; and the list reporter printed
      `qa-reach-batch.spec.ts:1290` for a test whose JSON report said 1448
      and whose source says 1448. Nothing was misdiagnosed in that pass —
      both CI-red tests reported their true line — but the job log is the
      ONLY channel into a red CI shard, so a reader chasing a line can land
      in the wrong test, and `e2e-verdict.py`'s list-output fallback path
      would carry the wrong number into the verdict block. FIX: find the
      mechanism (transform-cache state is the obvious suspect and is
      unproven), and meanwhile make the verdict block identify tests by
      TITLE with the line as secondary. ACCEPTANCE: the verdict names a
      test the reader can find, demonstrated on a run that reproduces the
      drift. [src: qa-tester CI-4 pass, 2026-08-29]

- [ ] (P3, XS) **INVARIANTS-PROJECTION-1 — the camera-projection helper
      `projection.spec.ts` uses privately now has a second real use, this
      repo's own stated threshold for extraction.** kind: capability
      (DRY — CLAUDE.md: "extract on the second real use, not the first
      imagined one"). Flagged by the SEL-6 qa-tester agent (`153681b`) while
      building `qa-sel6-verify`'s occlusion-region control: it needed the
      same orthographic/perspective camera-projection reasoning
      `projection.spec.ts` already carries privately, and duplicated the
      minimum needed rather than importing it, since it lives in a spec
      file, not a shared helper. FIX: move the helper into
      `apps/web/e2e/invariants.ts` (this repo's existing home for shared
      e2e assertions) and have both `projection.spec.ts` and
      `qa-sel6-verify`'s occlusion control import it. ACCEPTANCE: one
      definition, two call sites, no behaviour change (both existing specs
      stay green); a third future consumer needs no duplication to reuse it.
      [src: SEL-6 qa-tester agent report on `153681b`, filed by
      backlog-groomer pass 18]
      TERRITORY: `apps/web/e2e/invariants.ts`,
      `apps/web/e2e/projection.spec.ts`,
      `apps/web/e2e/pick-affordance.spec.ts` (or wherever
      `qa-sel6-verify` lives). agentType: frontend-builder or qa-tester.

- [ ] (P3, XS) **PGTEST-GATE-VACUOUS-NONGOAL — record, don't fix, the one
      case PGTEST-GATE's verdict deliberately leaves unfloored: PostgreSQL
      present but zero pg-requiring tests selected.** kind: process note
      (deliberate non-goal, not a gap to close). PGTEST-GATE (`ef5d1c5`)
      made a silent 37%-skip loud, but there is no failing floor for the
      vacuous case where a real server is available and the pg-marked tests
      happen to be deselected to zero (e.g. `-k` filtering them all out) —
      the verdict prints `NOTE: no test asked for a database this run` and
      the report/verdict cross-check refuses on disagreement, but a
      hardcoded "must serve >= N" count would rot the moment the suite's pg
      test count changes, becoming exactly the kind of gate-cannot-fail
      vacuity GATE-FLOOR exists to catch elsewhere. This item exists so a
      future pass does not "fix" the non-goal with a magic number: the
      correct floor for THIS case is the existing whole-suite test-count
      floor (`services/documents/tests/` collected count), not a
      pg-specific one layered on top of it. ACCEPTANCE: none — this ticket
      closes by staying a documented decision, unless a future audit finds
      the vacuous case actually masking a real regression, in which case
      re-open with that evidence.
      [src: PGTEST-GATE platform-builder report, 2026-08-28, recorded by
      backlog-groomer pass 18]
      TERRITORY: none (process note). agentType: n/a.

- [ ] (P3, S) **AUDIT-HOUSEKEEPING — bundle of small engineering-audit
      carry-overs (`docs/AUDIT-ENGINEERING.md` "Pass 7" M6(b)+M10), one
      slice, none urgent alone.** (a) `git worktree prune` + `git branch -D
      worktree-agent-*` at batch end — 16 abandoned worktrees measured at
      7.0 GB of 21 GB free, all sixteen verified 0 commits ahead of origin
      (nothing stranded); add the `rev-list --count origin/<branch>..
      <worktree-branch>` check to the loop's Integrate phase (the worktree
      sweep is the one item here with a clock on it — disk). (b) 23 of 100
      SHAs cited across ROADMAP+BACKLOG do not resolve to any commit object
      in this repo (`git cat-file -e <sha>^{commit}` fails) — a grooming
      sweep to prune or correct dead citations. (c) anchor
      `viewport-makeover.spec.ts:373`'s surviving `waitForTimeout(1200)` to
      a render-tick wait instead. (d) `check-compose.py:156-161`'s
      dev-overlay half is still a hand-list beside a half that sweeps every
      service — unify. (e) no `alembic check` fast gate for the gateway
      (1 migration, 1 table, `Base.metadata.create_all`-tested — model/
      migration drift is invisible until `deploy-path`; documents already
      has the equivalent). (f) `services/gateway/tests/
      test_assembly_import_chain.py:56` is the one place a kernel
      (`build123d`) import leaks outside `services/geometry` — move behind
      `pytest.importorskip` or a committed fixture file.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M6(b)+M10, filed by
      backlog-groomer pass 8]
      TERRITORY: `.claude/workflows/*.js` (Integrate phase), `docs/ROADMAP.md`
      + `docs/BACKLOG.md` (citation sweep), `apps/web/e2e/
      viewport-makeover.spec.ts`, `scripts/check-compose.py`, gateway
      alembic config, `services/gateway/tests/
      test_assembly_import_chain.py`. agentType: platform-builder.

- [ ] (P3, XS) **QA-REVIEW-OWNER — `docs/QA-REVIEW.md` is cited by ROADMAP
      and BACKLOG but owned by no agent, and `qa-tester.md` instructs
      "run the Playwright suite in both projects" when
      `playwright.config.ts` declares none.** kind: defect (process).
      MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 7" M9): `docs/QA-REVIEW.md`
      + `docs/PERF.md` are both 20 days stale with no agent definition
      writing them (`grep -rn QA-REVIEW .claude/agents/` → no matches),
      while `qa-tester` runs every non-kernel batch and its findings go into
      return reports instead of the repo. FIX: either give `qa-tester`
      `docs/QA-REVIEW.md` explicitly in its agent definition, or delete the
      file so nothing cites a document nobody maintains; fix
      `qa-tester.md:16-19`'s "both projects" instruction to match TOUCH-1's
      reality (no `projects` array exists). ACCEPTANCE: `docs/QA-REVIEW.md`
      either has a real writer or is deleted with its citations removed;
      `qa-tester.md` no longer asks for a step the config can't do.
      [src: docs/AUDIT-ENGINEERING.md "Pass 7" M9, filed by backlog-groomer
      pass 8]
      TERRITORY: `.claude/agents/qa-tester.md`, `docs/QA-REVIEW.md`,
      `docs/ROADMAP.md`/`docs/BACKLOG.md` citations. agentType:
      platform-builder.

- [ ] (P3, XS) **GQA-2 — a selector "authored before the GEOM-3 change" and
      "OCCT couldn't build the outer-wire region at pick time" produce the
      IDENTICAL stored signature, so a future document-side re-emit cannot
      tell them apart.** kind: defect. `_signature_dto` emits all three
      `outer_*` fields as `None` both when a pre-2026-08-16 selector never
      had them AND when `outer_boundary_invariants()` fails at pick time —
      the resolver keys the dual-read purely on field PRESENCE, silently
      taking the weaker inferred-band path in both cases. The wrapper
      already carries `selector_version: 1`, the field that exists to make
      this distinguishable, and it isn't used. Narrow today (needs a live
      OCCT region-build failure at pick time to matter) but will directly
      block a future document-side re-emit from knowing which stored
      selectors it has already upgraded. FIX: stamp `selector_version`
      (or a dedicated reason field) when the outer-boundary build fails,
      distinct from "never computed." ACCEPTANCE: a new test forces an
      OCCT region-build failure at pick time and asserts the resulting
      signature is distinguishable (by field, not just by None-ness) from
      one from a genuinely pre-GEOM-3 selector.
      [src: geometry-qa independent verification of GEOM-3, `0628ceb`,
      2026-08-16, docs/GEOMETRY-QA.md "GQA-2"]
      TERRITORY: `services/geometry/src/geometry/kernel/faces.py`
      (`_signature_dto`), `packages/py-kit` (schema, if a field is added).
      agentType: kernel-architect.

- [ ] (P3, XS) **GQA-3 — GEOM-3's tier 4a cost moved from the resolve path (a
      500x win, 1.70 us vs 4b's 866 us per candidate) onto the interactive
      viewport OVERLAY route, which is unconditional and wasn't in the
      builder's cost table.** kind: defect (perf regression, filed not
      blocking — two orders inside the ceiling). MEASURED warm, three
      goldens: `sketch-extrude-plate-6hole-ring-cut-60x60x10` 18.08ms ->
      21.71ms (+20%), `pattern-cut-6hole-boltcircle-60x60x10` 18.18ms ->
      21.52ms (+18%), `revise-lightened-plate-...-100x100x14` 15.65ms ->
      19.09ms (+22%). `planar_faces` runs on the overlay route — the one
      every viewport click hits, budgeted since audit H4 — not only on the
      GEOM-3 rescue path, so §12a's "a clean rebuild pays nothing" no longer
      holds there. Lever already measured and identified:
      `BRepBuilderAPI_MakeFace(gp_Pln, wire)` (0.249 ms) vs `Face(wire)`'s
      0.686 ms on the 64-hole face — swap the outer-boundary-invariant
      construction to the cheaper API on the overlay's hot path. ACCEPTANCE:
      the three named goldens' warm overlay cost returns to within 10% of
      pre-GEOM-3 baseline; `test_benchmarks.py` gains a tripwire for the
      overlay route specifically (the gap this pass found — cold-rebuild and
      isolated `planar_faces` benchmarks already exist but neither covers
      this route).
      [src: geometry-qa independent verification of GEOM-3, `0628ceb`,
      2026-08-16, docs/GEOMETRY-QA.md "GQA-3"]
      TERRITORY: `services/geometry/src/geometry/kernel/faces.py`
      (outer-boundary invariant construction), `services/geometry/tests/
      test_benchmarks.py` (new overlay tripwire). agentType: kernel-architect.

- [ ] (P2, XS) **GQA-4 — the golden corpus exercises `settle()`'s FAST path
      only; every defect SETTLE-2/SETTLE-3 found lived in the ladder the
      goldens never reach.** kind: capability (test-coverage gap). MEASURED
      (`docs/AUDIT-ENGINEERING.md` "Pass 9" N7): solving all 75 golden
      sketches through `PlanegcsSketchSolver` shows 70/75 route through
      `settle()`, and the batch changed zero golden bytes — evidence the
      fast path (`_try_hold_everything`) succeeds on all of them because
      their stored coordinates already solve. None exercises rungs 1-4, the
      orientation guard, or the drift condition — only the three new unit
      files' synthetic fixtures do. FIX: add a golden whose sketch is
      deliberately edited off its stored solution (one dimension changed,
      so the fast path must fail and the ladder must run), putting the
      ladder under the determinism gate for the first time. Also folds in
      N8(c) (`docs/AUDIT-ENGINEERING.md` "Pass 9"): one AST-swept test,
      `test_drawings_measure.py:898-910`, asserts only inside a loop over an
      unguarded filter (`for arc_like in (e for e in top.edges if …)`) —
      add a floor (`assert len(...) >= 1`) so an empty filter can't pass
      silently, mirroring `test_faces_geom3_qa.py:253`'s existing pattern.
      [src: docs/AUDIT-ENGINEERING.md "Pass 9" N7/N8(c), filed by
      backlog-groomer pass 11]
      TERRITORY: `services/geometry/goldens/**` (new fixture),
      `services/geometry/tests/test_drawings_measure.py`. agentType:
      kernel-architect.

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

- [ ] (P3, XS) **SEL-6-AFTERCARE (renamed groom pass 15 from a collided
      "SEL-8" id — the fillet edge-pick hover-highlight ticket also used
      SEL-8, filed later and unrelated; this is the older ticket) — five
      loose ends the review logged green** (`apps/web`). Filed 2026-08-08
      by the orchestrator. None blocks
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

- [ ] (P3, XS) **A11Y-SKETCHSTRIP-DUP-1 — three `SketchStrip` buttons now say
      the same thing twice, once in the name and once in the description.**
      kind: polish. Surfaced by A11Y-TOOLBTN-1's blast-radius enumeration, from
      Chrome's own accessibility tree on the real stack: `sketch-exit` announces
      name "Exit sketch and discard 4 unsaved entities — asks first" and
      description "discards 4"; `sketch-discard-confirm` name "…— this cannot be
      undone" and caption "cannot be undone"; `sketch-save` (bound) name "Finish
      sketch (edits are already saved)" and caption "edits save live". These
      `aria-label`s are NOT the ExportToolGroup workaround — they are deliberate
      FB-13 flow copy that predates the primitive fix and reads well on its own
      — so they were left alone rather than churned by a builder whose ticket
      was the primitive. The redundancy is the SAFE direction (both channels
      agree; many AT configurations suppress descriptions entirely), which is
      why this is P3 and not P2. FIX: decide per button whether the consequence
      belongs to the name or the description and say it once; the primitive's
      doc comment now states the rule ("do not fold a caption's words into
      `aria-label`"). ACCEPTANCE: no `ToolButton` in `SketchStrip.tsx` has an
      `aria-label` that repeats its own caption, and the FB-13 e2e cases still
      assert the consequence is announced somewhere.
      [src: frontend-builder, A11Y-TOOLBTN-1 measurement 2026-08-28]

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
- [ ] (P2, XS) **Fill in `e2e.yml:88` and `ci.yml:83`'s CI numbers**
      (`docs/AUDIT-ENGINEERING.md` "Pass 7" M5+M10) — orchestrator-only, a CI
      read no subagent can perform. Browser suite: 547 tests, ~20 min/shard
      extrapolated (was 352 when the "raise matrix to 6 past 30 min" rule
      was set; +55% in 20 days, 30 min/shard arrives in ~3 weeks —
      `e2e-shard-audit.py --timeline` has printed this on every run for ten
      days, unread). Python job: `just test` measured locally at 3735
      passed / 1 skipped / 1280.7s (21m20s), against a 30-min ceiling argued
      from ~2958 tests/14m31s. **Orchestrator-read CI number, groom pass
      26: the geometry (`python`) job ran 21m57s on a real CI run** —
      confirms the local 21m20s estimate rather than superseding it (both
      now inside ~2 min of each other), and the margin against the 30-min
      ceiling is ~27%, down from the original measurement's much wider gap.
      Still owed: read the latest green `e2e complete` job log for
      `--timeline` and the `python` job's Pytest step duration, and write
      both numbers into the two files' comments —
      the 30-min ceiling's own justification comment is still stale even
      though the number it argues for currently holds. [src:
      AUDIT-ENGINEERING.md Pass 7 M5+M10; CI reading groom pass 26]
- [ ] (P2, S) **RETRO §1.1's durable server-side Routine** — needs one
      founder approval, denied four times; the loop lost 58.3 hours between
      `5bfb528` and `22a44bb` (container reclaimed, restarted by hand, an
      8th recurrence) while the batch's own work rate was excellent (56%
      feat/fix). This is now the dominant term in throughput, not the work
      rate itself — "the single highest-value unblock available"
      (`docs/RETRO.md` §1.1), and the only item in either audit this batch
      the engineering org cannot fix for itself. [src: AUDIT-ENGINEERING.md
      Pass 7 M6(a); docs/RETRO.md §1.1]

## Done — archive

One line per item once its phase has closed (id, one clause, commit/evidence);
full narrative lives in the commit message and, where noted, `docs/CHANGELOG.md`.

### Groom pass 27 (2026-09-23, backlog-groomer — known e2e failures fixed, F-6 closed, gauge-lag closed)

- **F-6 (hole CREATE lets through a known-off-face point)** (`503473c`+
  `b99e4e4`+`37e6e18`) — a veto tried then withdrawn on measurement; the
  commit control now carries the placement warning live, and the X/Y
  fields' zero is named above them. Never filed as an open ticket; closed
  the same audit cycle it was found.
- **Gauge/panel one-commit lag** (`3b7f9ad`+`357b91e`) — `useGaugeFedForm`
  generalises the render-phase write fix (see CRAFT-13 follow-up above) to
  all nine gauge-fed mounts.
- **F-11 Fit while sketching** (`f9fcce6`) — the view rail's Fit key frames
  the open sketch instead of unmounting entirely; opened a real regression
  in its own wake (`CONSTRAINTS-GLYPH-1280-1`, filed AND closed same pass
  by `5444fa8` — a canvas click DRAWS while sketching, and the Fit bar's
  bottom-centre seat sat on the sketch rig's own -Y axis; moved to hang off
  the reference cube instead).
- **Next-step dot gains a word** (`bc53e7d`) — the band's resting proposal
  now speaks on hover/focus/once-per-step, reusing the viewport's own
  leader-note grammar.
- **REASON-GATE-1 straggler** (`17763b5`) — see REASON-GATE-1 follow-up
  above (`OffsetPlanePanel` was outside the original 15-editor survey).
- **GHOST-1 residual** (`0d96454`) — see GHOST-1 follow-up above (an
  unsplittable part stayed opaque during a sketch edit).
- **e2e known failures + shard-4 timeout** (`202cc9d`, `9375cb3`, `3b7f9ad`,
  `36360ae`, `8f8adc2`, `004755d`, `7c9ff95`, `5444fa8`) — see ROADMAP
  "Current focus"; CI verification owed.

Filed: CONSTRAINTS-GLYPH-1280-1 (closed same pass), QA-CUBE-YIELD-SETTLE-1,
FILLET-GAUGE-FPS-FLOOR-1, PATTERN-SCOPE-TIMEOUT-1,
SCREENSHOT-REFRESH-SKETCH-FIT-1, DATUM-DEADCODE-1,
SHORTCUT-SHEET-SKETCH-FIT-1, VIEWBAR-DRY-1, SKETCH-FIT-GRID-OCCLUDE-1,
NEXTSTEP-COMMENT-STALE-1, E2E-SHARD-COUNT-1 (see Ready/Next).

### Groom pass 25 (2026-09-15, backlog-groomer — Phase 5 flagship + gauntlet F1/F2 + CRAFT-13)

- **SCRIPT-1** (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`) — public Python
  scripting API, two-path-proven identical to a browser-driven build (12/12
  facts, byte-equal STEP/STL); `packages/loft-wire` split (33→15 deps).
- **F1 (wrong volume) + F2 (mesh_glb_id non-determinism)** (`f7cd483`) —
  adaptive integration at swept `VOLUME_EPS=1e-10`; cache paths unified.
- **CRAFT-13** (`b4e7821`) — root cause was a pointer-capture P0 (arc gauge's
  hit sleeve unmounting its capture host mid-drag), plus an unstated settle
  masquerading as the `craft9b-gauges` contract-β intermittent.
- **Air-gap claim** (`725bc4b`) — Swagger/ReDoc explorer pulled 3rd-party
  CDN/fonts on the self-hosted port; `docs_url=None`+`check-air-gap.py`.
- **Self-host web service** (`977f492`+`093dfc1`) — a `web` (nginx+SPA)
  service existed nowhere before; two guard-manufactured CI failures fixed
  en route (root-owned nginx pidfile, invalid job-level `runner` context).
- **Scorecard freshness gate** (`b1bb1b6`) — mechanical staleness check for
  `docs/VISION.md`'s scorecard, advisory only.

Filed: PERF-REAL-1, PERF-REAL-2, VEC3-DEDUP-1, CONTRACT-PARITY-TEST-1,
SCOREFRESH-PENDING-1, REQUIRED-QUERY-1, GAUGE-QUIESCE-1, NURBS-FIXTURE-1,
STEP-ROUNDTRIP-COVERAGE-1, PERF-REAL-3, AREA-INTEGRATION-1, GEN-CHECK-VERDICT-1,
DOCS-EXPLORER-1, CSP-1, PERF-ASM-1, PICK-ASM-1, BOM-ASM-1 (replaces the old
flat-BOM entry), FLOW-ASM-1 (see Ready/Next/Later). Full detail:
"Scorecard gaps" above and `docs/CODE-REVIEW.md`/`docs/GEOMETRY-QA.md`.

### Groom pass 20 (2026-09-13, backlog-groomer — frontend-redesign W0/W0REV/W2 reconciled onto BACKLOG)

- **W0REV modal-gate fix** (`da98622`) — one capture-phase `modalGate.ts` closes 3 findings: Enter-on-exit-prompt applying the armed dimension, save-in-flight focus loss, sketch drafts outliving sign-out.
- **FLOW-B1/B2/B3** (`d5e936a`, `78aaa67`, `fb63809`+`6097448`) — accelerators for the 5 core verbs, a solved-sketch Extrude proposal, one accented next-verb after a build.
- **CRAFT-6** (`a340ff5`) — the reference cube persists through plane-pick and sketch.
- **CRAFT-1/2/3** (`57d3bf8`) — a filleted body draws its edges, an orthographic view keeps its ground plane, the origin triad draws at rest.
- **MinIO repointed to quay.io** (`bd58416`, ROADMAP-only) — Docker Hub withdrew `minio/minio`/`minio/mc`; fixed 3 red CI jobs.

Filed: MINIO-LICENSE-REVIEW-1, FLOW-JOURNEY-GAP-1, GRIDMINOR-TONEMAP-1, MODALGATE-MIGRATION-1, AXISLABEL-ORTHO-1, VIEWFRONT-ORTHO-DECISION-1 (see Ready/Next). Full detail: `docs/CHANGELOG.md`.

### SEL-2 CLOSED (2026-09-04, frontend-builder)

- **SEL-2** — hover now names the entity a click will take (extended marker on a line with no closer point); one `CursorMark` serves drawing and selecting. Shots: `docs/screenshots/sel2-pick-marker-*-1280.png`.

### Groom pass 19 closures (2026-08-29, backlog-groomer — CI-4's original question answered, K2 + PBT-1 land)

- **K2** (backend-builder) — route-auth posture gate confirms gateway/documents/geometry posture already correct (four audit passes asked for this).
- **PBT-1** (kernel-architect) — sketch-solver 2000-trial seeded corpus; the 7-of-155 violated-constraint headline re-measures at 0. Found SOLVE-CRASH-1 (fixed below), SOLVE-CONFLICT-MOVED-1, SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (still open).
- **SOLVE-CRASH-1** (kernel-architect, arbitrated P2→P1) — an untyped 500 driving a circle's radius through zero: 3 real negative-radius solves fixed, 9 annihilated circles now return `sketch_conflicting`.
- **CI-4's original question** (qa-tester) — the e2e suite is NOT systemically unstable; shard 3/4 was structurally overloaded by Playwright's filesystem-order file cut. Two of three shard-3/4 reds root-caused; QA-CI4-MATE-1 (unreproduced hypothesis) remains.
- **CI-BAL** (platform-builder) — duration-aware shard split; corrected its own headroom claim 2.1x (local box) → 1.55x (real CI runner) — see SHARD-MANIFEST-CI-1.
- **QA-CI4-HEADROOM-1** (qa-tester) — cut a redundant-work cost first (a re-parked pointer costing 47% of one test's wall), raised ceilings second, from a measured distribution.
- **CI-5** (`2874f0a`) / **CI-5a** (`ecc1fb7`) (orchestrator) — a red shard's failure list now survives log-tail truncation and correctly distinguishes a declared `test.fail()` from a real failure.
- **PGTEST-GATE** (`ef5d1c5`, platform-builder) — a missing PostgreSQL now fails loudly instead of silently skipping 37% of the documents suite.
- **MEASURE-PROXY-1, PICKMARK-OCCLUDE-1, EXPORT-3, REACH-2-IMPORT-1, REACH-3-FLOW, REACH-2-FLOW, A11Y-TOOLBTN-1, HEM-1C, HEM-1D** (frontend-builder, 2026-08-28) — carried over from pass 18, collapsed into this archive here.

Filed: ARC-DEGENERATE-1, SHARD-MANIFEST-CI-1. Full detail: `docs/CHANGELOG.md`.

### SEL-8 CLOSED (2026-08-28, frontend-builder)

- **SEL-8** — the hover hit-test was intact all along; the highlight material lost the depth test against its own body surface and drew 0 px. Fixed with a two-pass `HighlightLines` draw; the same fix also unblinded MEASURE's identically-invisible edge highlight. See PICKMARK-OCCLUDE-1 for the half of the original finding this does NOT close.

### PANEL-DENSITY-1 CLOSED (2026-08-28, frontend-builder, founder-directed)

- **PANEL-DENSITY-1** — overlay panels (item tree, material selector) now match the header's density (row pitch 34.6px→24px). Fixed in `packages/design` primitives, not per instance; closed 3 pre-existing sub-24px touch-target violations in passing.

### Groom passes 15-18 closures (2026-08-27/28, backlog-groomer — reachability programme + HEM-1 P0)

Branch merged to `main` as `03d2eca` (141 commits, CI green) in pass 15; the reachability programme completed in pass 16 (`scripts/check-ui-parity.py`: 84/85 ops called, 97/109 literals authorable, 0 ABSENT-tier gaps — up from 39/120 literals unreachable at first measurement).

- **HEM-1** (`db05e13`, P0, wrong geometry) — a "closed" hem defaulted to the part's base-flange radius (a 6mm gap on 2mm sheet, labelled closed); now defaults to a small fraction of gauge.
- **ASMDRAW-FIT-1a** (`79ca41c`) / **ASMDRAW-FIT-1b** (`69b3ef7`) — assembly-sheet solved-extents route + fit-scale off it, not the picked scale; an unsolved bbox deliberately keeps the picked scale (user-owned, no-surprise posture — a decision, not an oversight).
- **EXTRUDE-COARSE-STEP-1** (`1661a5b`) — the extrude drag-handle keyboard step now quantises to the next step multiple instead of adding onto wherever a free drag left off; also fixed a queued-ack race dropping fast keypresses.
- **ORTHO-1** (`9a04a6a`) — an ORTHO/PERSP toggle + orienting commands (Home/Front/Top/Right/Iso, ViewCube picks) arm orthographic; closes a gap 4 consecutive audit passes reported.
- **REACH-ORDER** (`472f040`) — feature-tree reorder (drag + Alt+Up/Down keyboard), shipped-but-uncalled for weeks.
- **REACH-ASMDRAW** (`02bd6ab`, `3e2d1e5`) — an assembly can now be drafted on a drawing sheet with its numbered parts BOM.
- **FORCE-CLICK-AUDIT-1** (`6911352`) — 22 `force: true` e2e call sites audited: 18 were cargo (dropped), 1 was hiding a real `sr-only` visibility defect (fixed), 3 are genuine refusals (proven via new `clickRefusedControl` helper).
- **DRAWING-VERTEX-PICK-1** (`fe96d9b`) — a vertex handle now claims at most a third of its shortest incident edge, so the edge keeps a reachable middle at every length.
- **REVOLVE-1** (`1b28dd5`) — axis `<select>` offers all 3 world origin axes + profile edges; closed the last ABSENT-tier literal in the gateway contract.
- **SKETCH-VOCAB-1 frontend half** (`38e37f5`) — constraint catalogue lists all 16 verbs (was 12); kernel half shipped pass 14.
- **MATE-1** (`a2a6f9f`, gated `1ae3270`) — a buried mate face is reachable via `mateDepthStack`; closed T-13 (highlight = the face's own traced boundary). T-14 was out of scope, refiled as MEASURE-PROXY-1.
- **QA-R1** (`5957252`) — fixed `Flyout`'s label-collapse primitive, not the sketch strip instance it was first reported on.
- **QA-R2** (`0cee656`, e2e hardened `d2b1d26`) — the angle glyph now reads the solved value, not the authored placeholder.
- **QA-R4** (`278c122`) — `derivePartBuild` takes write-in-flight + the write's own reply as inputs so a body mid-write no longer reads a stale "Up to date"; also unified the SOLVE-2-class STATUS/SOLVE cell disagreement onto one predicate.
- **MATE-OBS** (`6b26ff7`) — a mate write's ~1.35s stale window no longer renders a settled answer over a superseded solve; MATE-OBS-2 (tree-panel badge, an eighth consumer) filed as a narrower follow-up.
- **Four REACH-3 follow-ups** (`ef704e7`, `1e8d8a3`, `f832eae`, `ddab149`) — a placing ghost reads its own number, the offset nudge quantises instead of accumulating drift, a placed dimension is re-grabbable, and drawing pick hit-regions are real shapes instead of bare zero-height SVG strokes.
- **SEL-8 id collision** — an unrelated P3 item that also used the id `SEL-8` renamed to **SEL-6-AFTERCARE** to disambiguate.

Filed this batch: ASMDRAW-FIT-1a/1b, PLAYWRIGHT-TOUCH-1, EXTRUDE-COARSE-STEP-1, HEM-1B, REACH-2-IMPORT-1, MEASURE-PROXY-1, FORCE-CLICK-AUDIT-1, MATE-OBS-2, DRAWING-VERTEX-PICK-1, SKETCH-COVERAGE-1, SOLVER-DOC-1. Confirmed still open, unchanged: REACH-3-FLOW's orientation half, TITLEBLOCK-STAMP-1, EXPORT-3, NAME-2b, REACH-2-FLOW, QA-R3. Full detail: `docs/CHANGELOG.md`.

### Groom pass 14 closures — collapsed pass 16 (full detail: `docs/CHANGELOG.md`)

- **SPEC-9/SPEC-10** (`e8702d5`/`42f6bbd`) — two more CI-4(d)-class specs
  fixed (wait for armed state; assert the settled solve).
- **DOCTICK-GATE** (`bd09f5b`) — CI now judges a commit range for missing
  ROADMAP/BACKLOG ticks.
- **SNAP-5** (`ecdf9ad`) — a near-axis-aligned line authors horizontal/
  vertical at placement.
- **SIGNIN-1** (`bf65ddc`) — the sign-in sheet is a bounded, centred object
  (45% of frame vs. 5.2%).
- **T-23/DRAG-1** (`35027ef`) — extrude gets a draggable depth gauge.
- **PATTERN-1 frontend half** (`ec9c569`) — tree-row selection seeds
  `PatternParamsV1.scope`; flow gaps found by review filed as REACH-2-FLOW.
- **REVOLVE-1 kernel half** (`88b6074`) — three always-available world
  origin axes.
- **SKETCH-VOCAB-1 kernel half** — angle/diameter/midpoint/collinear/
  symmetric-two-lines-and-an-axis, kernel-only (frontend half stayed open).
- **Parts register resume band** (`cb2e43e`) — proposes "resume what you
  were doing"; a REBUILD-column regression reverted same-night (`d0b55b2`,
  the fix, not a regression to re-file — a health verdict is volatile
  per-row data, unlike a stable unit column; reasoning lives in-source at
  `showHealth` for the next person tempted by the same analogy).

### Groom passes 10-13 closures — collapsed pass 16 (full detail: `docs/CHANGELOG.md`)

- **SETTLE-PERF-1** (`eed8729`) — planegcs settle-ladder 883x faster (12,944ms
  -> ~15ms on a 48-line edit); removed a 90s-timeout DoS route. [kernel-architect]
- **DXF-4** (`b226ee4`) — flat patterns now carry through-feature circles via
  a shared 3D-to-developed map; screen and DXF cannot disagree. [kernel-architect]
- **DXF-5/T-16** (`cc35629`) — exported DXF declared metres on a millimetre
  file; one document factory now sets MM explicitly, gated on emitted bytes. [kernel-architect]
- **PICK-2** (`8384f1e`) — a bodyless tip feature no longer arms a PICKING
  badge over zero targets; one shared guard refuses with a stated reason. [frontend-builder]
- **FB-21** (`b505efe`) — the Z axis glyph pointed along kernel −Y from a
  scene/kernel frame mismatch; both now derive through `occtToSceneTuple`. [frontend-builder]
- **FB-9** (`92da971`) — verification only: already fixed by FB-7c, not
  FB-21; gated end-to-end for the first time. [frontend-builder]
- **NAME-2/T-21/T-8** (`c2700ee`) — edges had no tolerant durable tier
  (faces had four); `resolve_edge_durable()` closes both orphaning cases;
  the client-facing re-stamp chip filed separately as NAME-2b. [kernel-architect]
- **EDGEFLANGE-1** (`3fba5fd`) — an edge flange could fold off a sheet's own
  thickness edge and report Solved with no material to bend; candidates now
  filtered to real sheet faces. [kernel-architect]
- **MATE-1 kernel half GATED** (`287510f`) — locked three kernel-side
  preconditions on S-15's fixture (0 bad of 14 offered faces); S-15's repro
  is not kernel-side, ticket re-scoped to UI only (closed pass 15). [kernel-architect]
- **REPICK-1/T-22** (`4c98ee0`, e2e fix `b036acd`) — re-picking a face used
  to silently reset an authored hole placement to the new face's centroid;
  now RE-ANCHORED (position preserved) unless never authored. [frontend-builder]
- **SETTLE-2/SETTLE-3/CommandBand label-shedding** (`4fef60a`/`8b239e5`/
  `ae1cea0`) — two SOLVE-1 regressions (a plain solve could re-orient a rigid
  shape across its symmetry axis; a settle could sacrifice a circle's radius
  pinning its centre) fixed and audit-verified; an unrelated e2e width-probe
  break fixed by shedding command-band labels incrementally. [kernel-architect
  + frontend-builder]

### SOLVE-1 CLOSED (groom pass 10, 2026-08-22, `7183955`, kernel-architect)

- **SOLVE-1** — AUDIT-PRODUCT R-5/R-5b/R-5c, P0 wrong geometry. An under-constrained solve now HOLDS the input geometry: `_GcsBuild.settle()` pins every free input coordinate back to the author's value after convergence, so a value edit no longer drags geometry the edit never named. A 245x performance regression in the rescued patch was found and fixed in the same commit. `docs/RESEARCH.md` §2/§9 corrected — the "guess-dependent by design" claim for under-constrained solves is now false, the determinism gate is sequence-level. SNAP-5 filed underneath it (line-by-line drawing never infers H/V).

### EXPORT-1/2 + REGISTER-1/2 + VIEWCUBE-1 + DXF-2a/2b/3 + DIM-3 + ESC-2 + VISION-FIX-1 CLOSED (groom pass 8, 2026-08-21) — the founder's 2026-08-17 file-page/export directive

Reconciled from `docs/AUDIT-ENGINEERING.md` Pass 7 M2: 10 of the prior 56 open Ready tickets were already shipped and the board didn't know (0/27 commits in range ticked ROADMAP/BACKLOG) — see DOCTICK-GATE for the fix.

- **EXPORT-1** (`3a7c4ca`) — export `ToolGroup` reachable with the Inspector collapsed.
- **REGISTER-1** (`044f1f7`) / **REGISTER-2** (`e024daa`) — NAME column widened with ellipsis+title; default sort → last-worked descending, sticky header.
- **VIEWCUBE-1** (`c28fbbc`) — cube renders at 1280×800/1366×768.
- **DXF-2a** (`a915bf1`) / **DXF-2b** (`5bfb528`) / **DXF-3** (`fe72e4d`) — bend-table text off the BEND layer; profile-only flat-pattern export path; UTF-8-correct codepage (no more mojibake degree signs).
- **EXPORT-2** (`1880db2`) — 3MF + glTF/GLB added to `ExportFormat`.
- **DIM-3** (`71b04ef`) — Dimension's armed state gets a visible affordance surviving deselect.
- **ESC-2** (`6fbeca0`) — Escape handling calls the single shared cascade (FB-13 landmine defused).
- **VISION-FIX-1** (`6dfb597`, vision-steward) — Interop row retitled "(import + export)", assembly-import claim corrected.
- Process debt, unchanged: none of the above independently code-reviewed.

### RECT-1 + SNAP-2 + SNAP-3 + MIRROR-1 CLOSED (groom pass 7, 2026-08-17) — vision-steward's 2026-08-16 competitive cluster

- **RECT-1** (`6d0f456`) — a rectangle drawn without typing a value is now a closed profile at placement (rigidity authored unconditionally), not 4 numerically-coincident but topologically disconnected lines. Filed RECT-2 (should drawing alone persist a sketch?).
- **SNAP-2 + SNAP-3** (`c233a5b`, one mechanism) — a snap now carries the constraint address it took its coordinate from, so a grounded-looking corner no longer silently drifts on its first re-drive. Filed SNAP-4 (explicit Fix double-pinning an already-snap-grounded point → false OVER-CONSTRAINED).
- **MIRROR-1** (`a0cc3f7`) — the mirror-axis picker now picks datum entities too, so a sketch's own centerline is a valid mirror axis.
- None of the four independently code-reviewed — process debt.

### PICK-1 + GEOM-3 CLOSED (groom pass 6, 2026-08-16) — the two P0s pass 5 flagged as longest-waiting

- **PICK-1** (`2b266b1`) — a viewport pick now stamps the sub-shape's OWNING feature id, not the tip feature's, so a mid-tree fillet/shell/draft/hole/chamfer/edge-flange/hem can be re-picked for an edit. Not reviewed or QA'd at ship time.
- **GEOM-3** (`1e39c14`, geometry-qa PASS `0628ceb`) — tier 4 face-signature gained 3 optional outer-wire invariants, fixing the >40%-open-area boss-deletion re-anchor case. The project's first `geometry-qa` pass (7154+10197+1176 differential comparisons, 1859 differences, all explained). Filed GQA-1 (P2, invariant triple not rotation-invariant), GQA-2 (P3), GQA-3 (P3, perf).

### QAH-1 CLOSED (2026-08-15 evening, `c3019b6`)

- **QAH-1** — e2e's "renders while orbiting" failure was the render-clock COLLECTOR, not the product: a mutation-test constant (`// MUTANT: always 0`) had been committed as product code while reconciling a stopped agent's work without running its own e2e gate. Fixed; a second independent defect (`waitForQuiet`'s 20s budget failing under load) fixed in the same commit. Not the same defect as `8d5be24`'s `cameraPose` race (kept apart correctly).
- **Process lesson (kept — still applies to grooming):** the fix commit was an ANCESTOR of the groom pass's search range, so `git log <range>` found nothing and produced a confident, well-evidenced, WRONG "no commit touches this" conclusion. Re-deriving from git log is only as good as the window it searches; a truncated window makes "found nothing" look identical to "nothing to find." Caught by the orchestrator re-reading `git log` against the correct range.

### Groom passes 3-5 closures (2026-08-14/15, backlog-groomer) — c449235 review triage, DIM-1/QA7-1/GEOM-2/FB-19, the four founder 2026-08-01 sketcher reports

- **DIM-1** (`a810524`) — dimension VALUE field silently wrote wrong geometry (uncontrolled input, now ref-backed); gate band widened after ablation showed the original passing on a broken build ~1/3 of the time.
- **SNAP-1** — founder "snap points not working" was NOT a snap-detection bug (measured correct in every buildable configuration); closed as a duplicate of SKETCH-2.
- **SKETCH-2** (`5ceed6e`, follow-up `8f00dec`/`09cec01`) — origin/axes made selectable constraint targets via lazily-materialised pinned construction geometry; closed the blocking symmetric-about-a-datum-axis false-OVER-CONSTRAINED finding + QA-SK2-1 (fixture wasn't actually rigid) and QA-SK2-2 (modifier-click ordering). QA-SK2-3 and SNAP-2 filed separately.
- SKETCH-1, VP-1, VP-1a — all QA'd green (`6df1170`); still never independently code-reviewed (flagged, not re-filed — same debt class as K8).
- **Mutation/debug-marker CI gate** (`56297d2`, `scripts/check-mutation-markers.py`) — the grep-level guard QAH-1's root cause asked for; wired into `just lint` + CI.
- **QA7-1** (`db144d7`) — the SEL-7 Create-costs-nothing wait was vacuous and its two comparison arms sampled at different settle depths. QA7-1b (scanner gap) filed.
- **GEOM-2** (`8b95dac`, reviewed `57711c4`) — tier 4 (`enclosing_face_match`) anchors a planar face's identity on its OUTER boundary, fixing the thickness-edit-orphans-holes case; review quantified the honest limit → GEOM-3 (P0), GEOM-4/GEOM-5 (smaller follow-ups).
- **FB-19** (`f7c41d9`) — chrome density (`FieldRow`, label-beside-control primitive). Not reviewed/QA'd/screenshotted at ship time — tracked as FB-19b.
- **QA-VERIFY-1 CLOSED** — both specs it asked to verify (`sketch-orbit.spec.ts`, `sketch-reopen.spec.ts`) now run green.
- **SKETCH-1** (`30a9f3f`) — a saved sketch re-opens via `beginEdit` hydration; QA'd green, never code-reviewed.
- **VP-1** (`43c703c`) — orbit while sketching on the middle button; QA'd green (`sketch-orbit.spec.ts` 7/7), never code-reviewed. Fragile mechanism noted, not filed: it relies on r3f REPLACING rather than merging the `mouseButtons` prop — watch on any r3f/drei version bump.
- **VP-1a** (`32e5b87`) — Alt(Option)+left-drag orbit reaches trackpads; never code-reviewed. Follow-ups filed: VP-1b (undiscoverable gesture), QAH-1 (above).
- **c449235** (Dimension verb arms instead of dead-ending) — reviewed (`d6fc92b`, corrected two integration errors). Follow-ups filed: DIM-1, DIM-3, ESC-2, ESC-3.

### Backlog hygiene sweep (2026-08-14, backlog-groomer) — 104 shipped-but-unarchived items collapsed from a 2,850-line Ready

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
  copy shipped. CM-5 (body-scope mirror after a revolve/sweep/loft cut
  silently filled the void) fixed the same week, same class.
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

### Recently shipped — 2026-07-19 to 2026-08-11 (SEL-4/6/6b + CI-4 fixes, sketcher rework, drawings/assembly FINDINGS burn-down, sheet-metal v2, engineering-audit H/G findings)

Full narrative: `docs/CHANGELOG.md` §§"2026-08-08 to 2026-08-11", "2026-07-22 to 2026-08-01", "2026-07-19 to 2026-07-20", "2026-07-12". Items already one-lined in the hygiene-sweep entry above are not repeated here.

- SEL-4 (5 sub-slices) / SEL-6 / SEL-6b — one shared pick hit-test + hidden-body occlusion for every viewport verb (fillet/chamfer/measure/shell/draft/drill-anywhere/mates); independent QA PASS both times.
- CI-4 fixes — `--fail-on-flaky` guard hardened (backend-builder); `waitForRenders` r3f-render counter (frontend-builder); `sketch-visibility` AA-phase flake identified, not a regression (SPEC-4).
- FB-13/FB-14 — Escape no longer ends a sketch; plain click replaces the pick set (cascade unwinds one step at a time).
- QA3-1..6 — drill-anywhere-on-a-face (stated numeric frame, live material check, concentric snaps); NEMA-17 imported-STEP dogfooding pass found 2 P1s (cannot drill where you want; a sketch on an imported face has no reference to the import).
- **GATE-2** — a `.dockerignore` allow-list lost an entry (LIC-2 added a COPY source with no negation) and silently failed all 3 image builds, caught only by the slowest workflow; `scripts/check-build-context.py` re-implements moby's ignore-matcher to gate the whole class in `just lint`+CI.
- **#42/SH-1** — shelling a rib at exactly 2x the wall thickness left a zero-width slit and reported `ok`; now a typed `shell_thickness_too_large` via one shared predicate; knife-edge proved 1.999/**2.000**/2.001.
- **#31** — compose's projection-keyed anchors now refuse a repeated projection instead of silently dropping a view.
- N1/N2 (frontend, kernel) — a widened/resized part re-anchors its dimensions and iso views instead of dying/overlapping; layout-issues check strip + RE-ANCHORED badge + a typed reason beside an unresolved dimension.
- CONC-1/2/3 — gateway session affinity, bounded admission queue, honest 504-not-502 timeout (`docs/OPERATIONS.md` §6).
- GATE-1 — full Playwright suite on every push, sharded 4 ways with a coverage-reconcile job.
- OBS-1 — Prometheus `/metrics` for all 3 services, fail-closed outside dev (`docs/OBSERVABILITY.md`).
- N8/N4/#50/N5 (kernel) — assembly STEP now instances parts instead of deep-copying geometry (21 instances: 504KB→58KB); exports named after the document; tapped-hole callout reaches every export format; exported page background is white not grey.
- Mirror feature (kernel `MirrorFeature`/`MirrorParamsV1`, plane or datum axis) + web authoring — end to end.
- Assembly import response-amplification DoS closed — occurrence-count + total-byte caps, typed 422s.
- Assembly STEP import slices 1/2a (kernel) — XCAF reader hardened, CPU-bounded subprocess, editable single-body ingestion.
- Section views E1a — end-to-end wire (kernel); E1b (web authoring) landed later, both listed in the hygiene sweep above.
- Drawings D1-D4 — title-block author/date/notes, authored dimension placement honored, first-angle projection, assembly-view typed-422 (was an opaque 404); dead-capability sweep found 6 orphaned drawing capabilities total.
- Drawings note-render, DE-4 artifact cache, sheet-size picker (A4→A0+ANSI), MB-4c per-body lump count, raster e2e hardening (root cause: a stale pre-units-convention format string, not raster drift — only 1 real ≤2px band-fit tolerance found).
- Sheet metal WF-1/PB-1 (founder dogfooding) — cut-after-fold fold-back invariant, edge-flange width extents + auto bend-end relief + partial-width flat pattern; hem-on-a-flange-top now flat-patterns (TB-1 dogfooding); width-extents editor UI; corner-relief in-scene highlight.
- Sheet metal v2 #1/#2 + spike (kernel) — non-parallel depth-1 bend stars (2D plus/cross layout), depth-≥2 bend-tree unfold (box corner/return/Z, self-overlap typed-rejected), tractability spike proved TRACTABLE via recursive tree walk.
- STEP parse-timeout hardened — CPU-time `RLIMIT_CPU` ceiling + wall-clock liveness backstop, closes a CPU-contention flake without weakening the DoS guard.
- Regression A/B (code review) — resilient face re-match no longer silently moves the resolved plane origin on a tier-2 (coplanar) match; cut-aware mirror no longer silently no-ops a reflected removal that misses the body (falls back to `mirror_union`, which already carries the body's own cuts).
- H2/H3/H4/H5/CR-6 (AUDIT-ENGINEERING) — a sheet can no longer mix source documents/scales across views (typed 422s both layers); duplicate view-projection now unique-constrained at the DB; per-face provenance made opt-in + a linear spatial-hash matcher (was quadratic, 8.83s→1.82s at 4800 faces); sheets-per-drawing N+1 query fixed (3/sheet → 4 total); multi-sheet export filenames now name the sheet.
- FINDINGS #1/#2/#3/#3-fe/#9/#11/#12/#13/#16/#17/#18/#19/#20/#22/#23 — cut-aware pattern+mirror (silent-wrong-geometry pair), same-face reference resilience + re-pick repair affordance, per-face provenance enabler, undo bypassing cross-doc protection, negative-diameter guard, Esc/dimension-hint/per-feature-error-copy UX trio, unit-aware property readouts, multi-sheet drawings UI (+ drag-to-place, per-sheet compose/export), viewport interaction polish (topology-as-translucent-patch, NavCue, per-instance contact shadows), jargon/ergonomics pass, "New part" navigates into it.
- Audit G1/G2/G3/G4 — geometry S3 creds anchor-sourced from MinIO's; per-request work bounds (deflection/pattern/feature/instance/mate/interference/view/sketch/loft/selector caps) as typed 422s; compose port/credential hygiene; `scripts/check-compose.py` invariant guard.
- Fail-closed on default datastore credentials (publishing blocker) — a publicly-known default/blank DB/queue/object-store password now refuses to boot outside `LOFT_ENV=dev`, one inherited `model_validator` across all 3 services.
- Revolve construction-centerline axis (opens a half-profile); assembly interference/collision detection (N² pairwise `BRepAlgoAPI_Common`, typed never-500); assembly STEP export (AP214 product structure, byte-deterministic); drawings incumbent-parity matrix (12-item ordered campaign, WB-64-sourced).

### Phase 0/1/2 (through commit `a1c42be`) — scaffold through parametric core convergence

Full evidence: `docs/CHANGELOG.md`.

- Phase 0 — monorepo scaffold, py-kit bootstrap, service skeletons + compose, contract pipeline, web shell + first light, CI pipeline, geometry golden harness, community surface.
- Phase 1 — STEP/STL export, feature-tree persistence, sketch solver + UI, extrude, viewport rendering, fillet/chamfer, full-flow e2e gate.
- Phase 2 — topological naming design, construction geometry, tangent/perpendicular/parallel/equal/symmetric/concentric constraints, revolve, measurement, pattern; fillet/chamfer UI, trim/extend/offset/mirror, splines v1, sweep, loft; offset/datum planes, multi-loop closed profiles → holes; sketch-on-face, click-specific edge selection, shell, draft (**Part modeling ➖→✅**); STEP import v1 kernel-side; STEP import P1 security + gateway upload + UI picker (**Interop ❌→➖**); typed over-constraint diagnosis (#6); sketch dimension expressions (driving/driven); constrainable spline fit points v1.1 (**Sketching ➖→✅**); gateway auth-gate on geometry-compute routes (audit F7 P1 security); assemblies architecture decision endorsed.

### Phase 3-4b (through `a6a5814`, 2026-07-15 to 2026-07-19)

Full evidence: `docs/CHANGELOG.md`.

- Assemblies v1 — document model, `AssemblySolver` (numpy-only, no GPL), mate-geometry resolution, evaluation + shared-mesh tessellation, mate authoring UI, flat BOM (**❌→➖**).
- Drawings v1 — document model, exact-HLR projection, dimension measurement/provenance + authoring, SVG export (**❌→➖**); export DE-0…DE-3 — server-composed placement, PDF/DXF serializers.
- Multi-body modeling + booleans v1 (MB-0…MB-4c) — union/subtract/intersect between independently-built bodies, downstream fillet on a boolean-created edge, multi-lump bodies, multi-solid STEP import, guided `boolean_disjoint` recovery.
- Sheet metal v1 — base flange, edge flange (+ provenance), depth-1-bend-star unfold, flat-pattern drawing view + bend table (**❌→➖**).
- Performance benchmark suite + CI tripwires — two-tier gate (generous asserted ceilings + an opt-in median/p95 human-watched tier); infra half of the Performance ❌ row only, no ❌→➖ flip (the real-part corpus stayed open).
- Units (length) v1; Undo/redo v1 (server-side bounded snapshot rings, verbatim id-preserving restore); Viewport makeover batches 1-3 (full-bleed canvas + atmosphere + matcap shading, decorative-chrome deletion, in-command depth/hover feedback); Datum-plane completeness (midplane + offset-chaining kinds); mesh-store MinIO/S3 swap, STEP re-parse cache, Redis-backed rate limiting.

## Changelog

- 2026-09-23 — **Groom pass 27 (backlog-groomer):** e2e known-failures +
  shard-4 timeout root-caused and fixed (6+1 commits, CI verification
  owed); F-6 and the gauge/panel lag CLOSED; 11 items filed. See "Scorecard
  gaps" above and BACKLOG Done archive for full detail.
- 2026-09-23 — **Groom pass 26:** CRAFT-12/VEC3-DEDUP-1/CSP-1 CLOSED;
  adjacency tier 3 shipped; VISION re-scored twice; 5 items filed. See
  "Scorecard gaps" above for full detail.
- 2026-09-15 — **Groom pass 25 (backlog-groomer):** SCRIPT-1 (public Python
  scripting API), F1+F2 (gauntlet volume/determinism defects) and CRAFT-13
  CLOSED; 16 items filed (perf/gauntlet, code-review P1s, Assemblies wave).
  See "Scorecard gaps" above for full detail.
- Passes 7-24: full reachability programme, CI hardening, SOLVE/PBT/SEL-2/
  ARC-BRANCH-1 clusters, Wave 3 close-out, frontend-redesign wave-log
  reconciliation. Full detail: `docs/CHANGELOG.md`.
