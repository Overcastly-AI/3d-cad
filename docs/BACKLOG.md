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

- [ ] (P1, S) **W0REV-3** — sketch drafts are never swept: `DRAFT_MAX_AGE_MS`
      is checked only on read of that one key, so 50 parts leave 50 buffers on
      disk indefinitely. A full quota then degrades `auth/session.ts`
      silently, which reads as "logged out on reload" and will never be traced
      here. Needs the storage seam widened to allow a key scan [W0 code
      review, 2026-09-12]

- [ ] (P2, M) **W0REV-5** — the unsaved-sketch guard lives inline in
      `PartPage.tsx` (~5,690 lines) rather than the `useUnsavedSketchGuard`
      hook the audit specified, so the two order-dependent effects,
      `unsavedSketchRef` and the `leaveSaving` machine have ZERO unit coverage
      — protected by a comment that overclaims: reorder them and the first
      exit may go unguarded QUIETLY, not loudly [W0 code review, 2026-09-12]

- [ ] (P2, M) **W0REV-6** — third hand-rolled modal shell; `LeaveSketchPrompt`
      duplicates `ShortcutSheet` nearly line for line (backdrop,
      stopPropagation, tabIndex, focus save/restore, header band). Per
      "extract on the second real use" this is the trigger, and the extraction
      is where the modal key-gate and focus management belong ONCE [W0 code
      review, 2026-09-12]

- [ ] (P3, S) **W0REV-7** — "Dismiss" on the restored-draft note only hides
      the banner; the draft stays and the sketcher stays open on a buffer the
      user may not have wanted back. Ambiguous exit inside the feature whose
      whole thesis is unambiguous exits [W0 code review, 2026-09-12]

- [ ] (P2, S) **W0REV-9** — the buffered replay path has no test that can fail
      on it: the e2e gates the OUTCOME, which is identical whether the
      buffered or the mounted path ran, so on a fast enough machine the buffer
      code is never exercised and the suite still passes [W0 code review,
      2026-09-12]

- [ ] (P3, S) **W0REV-10** — Tab as the very first key diverges between the
      two paths: mounted focuses cell 0, buffered replays to cell 1. Same
      keystroke, two answers, decided by a race [W0 code review, 2026-09-12]

- [ ] (P3, S) **W0REV-11** — two tabs on one part cross-restore: tab 1 writes
      the draft, tab 2 restores it and announces "Draft restored" for work
      that was never lost; both then mirror and both can save it [W0 code
      review]

- [ ] (P2, S) **DIMEDIT-KEYS-1** — the THIRD address of the dropped-keystroke
      family: `dimension-editor`'s cell is also inside a commit that trails
      the click opening it. Unmeasured — FLOW-A1 could not check it, `routes/`
      was held by a sibling [FLOW-A1 builder report, 2026-09-12]

- [ ] (P2, M) **CUBE-SKETCH-OCCLUDE-1 — during ordinary sketching, the
      reference cube's 108x108 seat in the bottom-right silently eats gestures
      aimed at the scene underneath it.** ACCEPTANCE: a decision recorded in
      `docs/design/REDESIGN-ROADMAP.md` or `docs/VISION.md` with its
      reasoning, and either the cube gains a yield mechanism for drawing or
      the trade is documented as deliberate with a regression test pinning
      today's behaviour. Cross-reference: CRAFT-6 (`a340ff5`) made the
      original trade; VIEWFRONT-ORTHO-DECISION-1 is the same shape — a
      deliberate behaviour nobody actually decided deliberately. [src:
      cross-wave QA + `d0a3190` follow-up, 2026-09-13, `docs/QA-REVIEW.md`]
      TERRITORY:
      `apps/web/src/viewport/armedPicks.ts`, `apps/web/src/components/AuthoringViewCube.tsx`, `apps/web/src/viewport/ViewCube.tsx`.
      agentType: frontend-builder (decision may need founder/vision-steward
      input first, same as VIEWFRONT-ORTHO-DECISION-1). (history:
      docs/BACKLOG-ARCHIVE.md#item-cube-sketch-occlude-1)

- [ ] (P3, S) **CRAFT-INTERMITTENT-1 — one of its two cases is now CLOSED, and
      the closure PARTIALLY REFUTES this ticket's own classification.**
      ACCEPTANCE (rect-rigidity only, going forward): root-cause it under CPU
      load, matching the discriminator that worked here, before concluding it
      is unreproducible. `6043601`'s verdict-block fix means the next
      occurrence will name its own cause — use that first. [src: CRAFT-7 wave
      report, 2026-09-14; reconfirmed groom pass 23; `:253` half closed and
      `:592` half split out, groom pass 27] TERRITORY:
      `apps/web/e2e/rect-rigidity.spec.ts`. agentType: qa-tester /
      frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-craft-intermittent-1)

- [ ] (P2, M) **ESLINT-HOOKS-1** ACCEPTANCE: `react-hooks` added to
      `eslint.config.js`; every violation either fixed or exempted with a
      one-line reason at the call site; `just lint` stays green. Worth doing
      now — Wave 3 is adding a lot of hook-heavy viewport code and each new
      gauge (CRAFT-9/10/11) is a fresh chance to repeat CRAFT-8's bug. [src:
      CRAFT-7 wave report, 2026-09-14] TERRITORY: `apps/web/eslint.config.js`
      + violations repo-wide. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-eslint-hooks-1)

- [ ] (P2, S) **EXTRUDE-RAIL-ESCAPE-1** ACCEPTANCE: the rail field's Escape
      matches the gauge cell's — cancels the unsaved edit and reverts the
      field, not the whole command — with a regression test covering both
      controls. [src: CRAFT-7 wave report, 2026-09-14] TERRITORY: extrude rail
      field component (wherever `ExtrudeDragHandle`'s sibling numeric-entry
      lives). agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-extrude-rail-escape-1)

- [ ] (P2, M) **CRAFT-14 — every `disabled={someTransientFlag}` is a latent
      dead end.** ACCEPTANCE: audit by the QUESTION (is this a refusal or a
      delay?), never by grepping the idiom — the last three defect-class
      audits that matched a shape missed every instance wearing a different
      one. Do NOT change the primitive first: the swallow is correct for
      genuine refusals; only add a distinguishable state for transient ones,
      once the audit names which call sites need it. [src: Wave 3 close-out
      finding 4, 2026-09-14] TERRITORY:
      `packages/design/src/primitives/ToolButton.tsx` + call sites repo-wide.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-craft-14)

- [ ] (P2, S) **CRAFT-15 — 3 of 12 points along a picked edge were already
      unreachable before any gauge mounted.** ACCEPTANCE: reproduce on a
      control edge with no gauge attached, root-cause the 3 unreachable
      offsets (occlusion, hit-box shape, or z-order), and fix or document why
      they are structurally unreachable. [src: Wave 3 close-out finding 5,
      2026-09-14] TERRITORY: `apps/web/src/viewport/PickMark.tsx`, edge
      overlay. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-craft-15)

- [ ] (P2, S) **CRAFT-16 — should the shell gauge seat at the RIM rather than
      the face centroid?** ACCEPTANCE: a decision recorded here or in
      `docs/design/REDESIGN-ROADMAP.md`, and if rim-seating wins, a builder
      moves CRAFT-9b's gauge anchor accordingly with before/after screenshots
      (CLAUDE.md design mandate rule 4). [src: Wave 3 close-out finding 6,
      2026-09-14] TERRITORY: `apps/web/src/viewport/**` (shell gauge anchor).
      agentType: frontend-builder (decision may need founder/vision-steward
      input first). (history: docs/BACKLOG-ARCHIVE.md#item-craft-16)

- [ ] (P2, S) **CRAFT-17 — two competing e2e helper extractions must converge,
      and their `reach()` now mean DIFFERENT things — sharper than tidiness.**
      ACCEPTANCE: `gaugeReach.ts`'s callers move onto
      `gaugeProbe.ts`, `gaugeReach.ts` deleted, no behavior change (same reach
      numbers before/after on the specs that used it); if BOTH measurements
      (chord and polyline) are genuinely wanted, name them for what they are
      rather than overloading one `reach()`. [src: Wave 3 close-out finding 7,
      2026-09-14; sharpened by code review P2-7,
      `docs/CODE-REVIEW.md`, `451245c`] TERRITORY:
      `apps/web/e2e/**` (gauge spec helpers). agentType: frontend-builder /
      qa-tester. (history: docs/BACKLOG-ARCHIVE.md#item-craft-17)

- [ ] (P2, S) **GAUGE-PROPORTION-1 — the rod-vs-graduation proportion problem
      generalizes past the 2 mm case CRAFT-7 fixed.** ACCEPTANCE: a rule
      relating rod diameter to graduation pitch (not just screen-space
      spacing) that holds at both measured extremes, with a before/after
      screenshot pair per CLAUDE.md's design mandate rule 4 (a screenshot is
      the check that catches "present, correctly sized, invisible"). Relevant
      to CRAFT-9a/9b/10/11 — any of the four dispatched gauges can hit either
      extreme on a real part. [src: CRAFT-7 wave follow-up, groom pass 23,
      2026-09-14] TERRITORY:
      `packages/design/src/gauge.ts`, `apps/web/src/viewport/ ParametricGauge.tsx`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-gauge-proportion-1)

- [ ] (P2, S) **FORMATANGLE-MIGRATE-1 — migrate the three hand-written angle
      formatters onto `formatAngle`.** ACCEPTANCE: all three call sites format
      through `formatAngle` with the same `unitSuffix` option `formatLength`
      already has; no behavior change (same rendered text for the same value)
      — a pure DRY convergence, proven by a snapshot/unit test per site
      showing identical output before/after. [src: DIRECTION-W3-PROPOSALS.md
      §11.5, CRAFT-8 follow-up] TERRITORY:
      `apps/web/src/measure/geometry.ts`, `apps/web/src/features/revolve.ts`, `apps/web/src/features/hole.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-formatangle-migrate-1)

- [ ] (P2, S) **IMPERIAL-LADDER-1 — should the imperial snap ladder be a
      binary series?** ACCEPTANCE: measure the ladder against a real
      inch-dimensioned part (drawn distances that land on 32nds), state which
      series a working engineer's eye actually wants, and implement that
      choice with the reasoning recorded in `docs/design/ REDESIGN-ROADMAP.md`
      or this ticket — do not ship a silent default. [src:
      DIRECTION-W3-PROPOSALS.md §11.7] TERRITORY:
      `packages/design/src/ gauge.ts` (ladder selection), `apps/web/src/routes/units.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-imperial-ladder-1)

- [ ] (P1, S) **GAUGE-TOUCH-1 — a touch pass on all nine shipped gauge mounts,
      W3-exit QA gate.** ACCEPTANCE: a real touch-emulated pass (Playwright
      touch input or an actual touch-capable device) on the extrude gauge and
      at least one of fillet/chamfer, shell/datum, revolve/draft, pattern,
      asserting the drag actually moves the value under touch pointer events,
      not just that the box is large enough. **Wave 3 is closed on the board
      this pass (groom pass 24, per orchestrator direction) with this gate
      still open** — noted as a tension, not resolved silently: the wave's
      build work is done and none of the nine open follow-up findings
      (CRAFT-12..17) block dispatching Phase 5 work in parallel, but this QA
      gate is real and still owed. Dispatch qa-tester on this alongside Phase
      5 work, not instead of it. [src: DIRECTION-W3-PROPOSALS.md §11.4;
      reconfirmed groom pass 24, 2026-09-15] TERRITORY:
      `apps/web/e2e/**` (gauge specs), touch harness (see PLAYWRIGHT-TOUCH-1
      for the existing harness-gap item this may share infrastructure with).
      agentType: qa-tester. (history:
      docs/BACKLOG-ARCHIVE.md#item-gauge-touch-1)

## Scorecard gaps (docs/VISION.md daily-driver scorecard)

See VISION.md's table for current row text — the vision-steward re-scores it
independently each pass; this note only points the queue at it, no
duplication. **Pass 8-19 detail moved to `docs/CHANGELOG.md` / Done archive.**

- **Groom pass 29 (2026-09-24, backlog-groomer) — the e2e root-causing batch
  is CI-confirmed green through `d3d0446` (8 jobs, 0 failed); PICK-PROXY-COLLIDE-1,
  CONTRACT-PARITY-TEST-1, PERF-REAL-2, E2E-SHARD-COUNT-1 and
  QA-CUBE-YIELD-SETTLE-1/FB-7 all CLOSED.** `9404cb1` fixed pick-mark seat
  publishing, buried-mark drawing and gauge/proxy occlusion (census: 0 lies,
  up from 7 live-but-buried on Fillet alone); `647f939` closed the
  contract-parity gate's own blind spot (expected set now derived from the
  OpenAPI doc directly, 0 mismatches over 86 ops) and confirmed
  `part.py:317` was already fixed by `43c03a1`, not deliberate.
  `09416c6`+`4fcb108`+`560eab1`+`8e9e5c8`+`8077ede`+`83e3c67` shipped
  PERF-REAL-2's checkpoint ladder (edit #249 34.1s→1.85s, 18.5x, QA-measured)
  with both caches now bounded in heap bytes (ladder 64 MiB, frontier 128
  MiB + one live oversize checkpoint held alone) — the early-edit floor
  (editing near the tree's start) is UNCHANGED and refiled as PERF-REAL-2B,
  needing a dependency-aware evaluator, not a bigger cache. `d3d0446` raised
  the e2e shard matrix to 6 (~22.6 predicted CI-min/shard, 1.77x headroom),
  confirmed on a real run by `55df4d3`. `d0604c5`+`856e3c0` root-caused the
  shared camera-rest-elevation nondeterminism behind both the FB-7 CI flake
  and QA-CUBE-YIELD-SETTLE-1: a sketch-exit fit reading the restore ease's
  in-flight direction instead of its committed destination (27-34°
  depending on load); rest elevation is now 23.11°, 0.00° off, in all 9
  CPU×latency combinations tried. Filed 6 items (GAUGE-READOUT-TAG-1,
  FACE-HOVER-BORE-FLAKE-1, PERF-REAL-2B, FRONTIER-OVERSIZE-SIDESLOT-1,
  PICK-SPEC-REWEIGH-1, LADDER-PROVENANCE-WEIGH-1) — see Ready/Later. `e2e`
  runs for `8077ede`/`83e3c67` still in flight at write time. No scorecard
  row flips this pass (correctness/perf hardening, not new capability).

- Passes 19-27: full narrative moved to
  docs/BACKLOG-ARCHIVE.md#scorecard-gaps-history-25-19 (2026-09-23 structural
  prune, extended pass 29). Headline: Phase 5 flagship (SCRIPT-1) and the
  gauntlet volume/determinism P0s (F1/F2) shipped; CRAFT-13 closed; Wave 3
  closed; adjacency tier 3 shipped; the e2e known-failure batch (pass 27)
  root-caused and fixed.
- **Prior passes (8-18):** reconciled in `docs/CHANGELOG.md` / Done archive.
  Still true and still open: `docs/GEOMETRY-QA.md`/`docs/UI-REVIEW.md` are
  stale against the last nine batches — dispatch `geometry-qa` and
  `frontend-qa` next batch.

## Ready (top of queue)

**Dispatch order, groom pass 29 (2026-09-24) — CI is green through `d3d0446`
(8 jobs, 0 failed, orchestrator-confirmed `55df4d3`); the `e2e` runs for
`8077ede` and `83e3c67` are still in flight.** PICK-PROXY-COLLIDE-1,
CONTRACT-PARITY-TEST-1, PERF-REAL-2 and E2E-SHARD-COUNT-1 CLOSED this pass —
see Done archive. PERF-REAL-1 (re-measure before re-ranking) and the
remaining product-audit findings (EDGE-RESOLVE-WARN-1, MEASURE-LABEL-PITCH-1)
lead — correctness/interaction-cost risk still outranks craft polish. Ranked,
disjoint, parallel-dispatchable; MINIO-LICENSE-REVIEW-1 and
CUBE-SKETCH-OCCLUDE-1 are both decisions before they are build tasks — the
first to the licensing custodian/founder, the second may need
founder/vision-steward input on the options before a builder picks one:

- [ ] (P1, M) **PERF-REAL-1 — 55-73s to select one face, 12.6-14.7s to open a
      real imported part.** ACCEPTANCE, updated: re-measure `just gauntlet` on
      `gearbox-11752` first (this may already materially close the ticket); if
      the settle time is still an order of magnitude off, the remaining lever
      is a different pick mechanism (canvas raycast instead of per-face DOM
      overlay) rather than further portal-host tuning. State the before/after
      numbers; do not declare victory on a toy part. [src: geometry-qa
      gauntlet, `docs/GEOMETRY-QA.md` 2026-09-15; progress `9083f0a`, groom
      pass 26] TERRITORY: `apps/web/src/viewport/**` (face-pick overlay).
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-perf-real-1)

- [ ] (P1, S) **MINIO-LICENSE-REVIEW-1** ACCEPTANCE: a licensing-custodian
      pass (or founder decision) records a verdict in `docs/LICENSING.md` —
      either "aggregation, no entry needed, here is why" or "here is the
      entry, and here is what changes if we ever build our own MinIO image."
      Do not resolve silently either way. [src: orchestrator, `bd58416`
      follow-up, 2026-09-13] TERRITORY:
      `docs/LICENSING.md`, `docs/RESEARCH.md` §8. agentType: oss-curator /
      founder decision. (history:
      docs/BACKLOG-ARCHIVE.md#item-minio-license-review-1)

- [ ] (P2, M) **FLOW-JOURNEY-GAP-1** ACCEPTANCE: either (a) a second
      canonical-journey spec that uses the accelerators + chip + accent end to
      end, with `check-flow-cost.py` reporting BOTH numbers (toolbar-path vs.
      accelerated-path) so the delta is visible and honest, or (b) the
      existing journey updated to take the shortest correct path with a
      documented reason for any step that must stay toolbar-driven.
      Regression: the toolbar-only number must not silently disappear. [src:
      FLOW-B1/B2/B3 integration, orchestrator report, 2026-09-13] TERRITORY:
      `scripts/check-flow-cost.py`, `apps/web/e2e/full-flow.spec.ts` (or a new sibling spec).
      agentType: frontend-builder. **ADDENDUM, groom pass 23 (stated
      prediction, not a new regression):** the 30-gesture number will not move
      for the WHOLE of Wave 3, on any pass, and that is not grounds to
      distrust the metric — `--journey fillet` reads 3 gestures today and a
      gauge version also reads 3. The metric models an expert who already
      knows every verb; it is structurally blind to what W3 buys, which is
      legibility for an engineer who does not know what 5 mm of fillet looks
      like on THIS part until they drag it and see (same gesture count, forty
      seconds versus two). W3's real evidence is screenshots, per-verb reach
      counts and the contract-β release test, not this number. [src:
      DIRECTION-W3-PROPOSALS.md §12 / groom pass 23 dispatch brief] (history:
      docs/BACKLOG-ARCHIVE.md#item-flow-journey-gap-1)

- [ ] (P2, M) **GRIDMINOR-TONEMAP-1** ACCEPTANCE: grid minor lines measure a
      contrast delta against the background consistent with the major lines'
      own ratio (state the number), AND `part-visibility.spec.ts`'s ghost
      census stays under its existing ceiling — fix the census's colour-space
      assumption (premultiplied vs. straight) rather than trading one gate's
      pass for the other's fail. [src: CRAFT-1/2/3 agent measurement,
      2026-09-13, docs/design/AUDIT-CRAFT-2026-09.md] TERRITORY:
      `apps/web/src/viewport/**` (grid material/tone-mapping), `apps/web/e2e/part-visibility.spec.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-gridminor-tonemap-1)

- [ ] (P2, M) **MODALGATE-MIGRATION-1** ACCEPTANCE: migrate the 22 named
      listeners onto `useModalLayer`/
      `modalGate` (or the `activationKeyOwner` seam, whichever applies), each
      with the same alarm-probe coverage `da98622` gave the first registrant.
      A regression test proves a stray key while ANY registered layer is open
      cannot reach the sketch behind it. [src: brief item 7 / da98622
      follow-up, 2026-09-13; progress `6602ccd`, W2 review, 2026-09-13]
      TERRITORY: `apps/web/src/lib/modalGate.ts`, plus the 22 files named by
      `modalGate.audit.test.ts`. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-modalgate-migration-1)

- [ ] (P2, S) **AXISLABEL-ORTHO-1** ACCEPTANCE: reproduce first on current
      HEAD; with origin/datums enabled, switch to front-orthographic and
      assert the three axis-label elements are present in the DOM at the same
      measured presence as the default view. If a legitimate reason exists for
      a label to retire in that view, state it and gate the absence
      deliberately instead of leaving it unexplained. [src: CRAFT-1/2/3 agent
      measurement, 2026-09-13] TERRITORY:
      `apps/web/src/viewport/OriginGeometry.tsx` (or wherever axis labels are drawn).
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-axislabel-ortho-1)

- [ ] (P2, S) **VIEWFRONT-ORTHO-DECISION-1** ACCEPTANCE: a decision recorded
      in `docs/design/REDESIGN-ROADMAP.md` or `docs/VISION.md` with its
      reasoning; if named views keep the ortho side effect,
      `view-projection`'s own affordance must not contradict it; if decoupled,
      `viewCommands.ts` changes accordingly with a regression test. Relevant
      to CRAFT-21 (Home restores projection; ViewCube re-fits) — coordinate so
      the two do not re-litigate the same seam twice. [src: CRAFT-1/2/3 agent
      finding, 2026-09-13] TERRITORY: `apps/web/src/viewport/viewCommands.ts`.
      agentType: frontend-builder (decision may need founder/vision-steward
      input first). (history:
      docs/BACKLOG-ARCHIVE.md#item-viewfront-ortho-decision-1)

- [ ] (P2, M) **CUBE-SKETCH-OCCLUDE-1** — full ticket in the wave log above
      (this pass's cross-wave QA finding). A product decision on whether the
      reference cube's pick-armed pointer-yield (`d0a3190`) should extend to
      ordinary sketch drawing, not just armed picks.

- [ ] (P1, M) **CRAFT-9c — now leads the Ready queue.** ACCEPTANCE: same as
      CRAFT-9a/9b (drag/arrow-key/reach/contract-β) plus a companion-cell
      check — dragging depth does not move the Ø cell's own displayed track
      and vice versa. §8.4 preview gate: the bore circle and the depth plane,
      or defer to W5. [src: DIRECTION-W3-PROPOSALS.md §8.3/§9] TERRITORY:
      `apps/web/src/viewport/**` (gauges), `apps/web/src/components/HoleEditor.tsx`.
      agentType: frontend-builder.  ~~**CRAFT-12-READPROPOSAL-1**~~ — **CLOSED
      (`5274bea`), same day as filed.** `readProposal` returned the whole
      `command-layer` group's world box; annotation roots (SketchScene,
      MeasureOverlay, EdgePickOverlay, FacePickOverlay, ShellFaceOverlay,
      HolePointOverlay, BendHighlightOverlay, FlangeSpanOverlay) now carry a
      tag `proposalBoxOf` skips. Measured both directions on the fixture this
      ticket cited: a resting sketch 100 mm away no longer triggers a re-fit
      on gauge release (297.0 mm camera travel -> 5.5 mm, the residual being a
      LEGITIMATE re-fit — the arrow itself pokes past the already-filled
      frame); a genuinely out-of-frame proposal (10 mm body, 300 mm extrude)
      still fires (550.5 mm travel). 5 new unit cases, each verified to redden
      under a mutant. (history: docs/BACKLOG-ARCHIVE.md#item-craft-9)

- [ ] (P2, XS) **GAUGE-READOUT-TAG-1 — the gauge readout has no `data-gauge`
      of its own, so `GaugeKeepOuts` finds it by string-matching the bare
      `<id>-readout` testid instead of one selector.** ACCEPTANCE: tag
      `GaugeTag` in `ParametricGauge.tsx` with `data-gauge={gaugeId}` (or an
      equivalent marker) so the keep-out pass is one `[data-gauge]` query, not
      a grip/sleeve query plus a same-id testid lookup; no change in which
      elements are kept out (same reach numbers on `pick-proxy-collision.spec.ts`
      before/after). [src: `9404cb1` report (PICK-PROXY-COLLIDE-1 follow-up),
      filed by backlog-groomer pass 29] TERRITORY:
      `apps/web/src/viewport/ParametricGauge.tsx`,
      `apps/web/src/viewport/useEdgeMarkAnchors.ts`,
      `apps/web/src/viewport/useSurfaceMarkBurial.ts`. agentType:
      frontend-builder. (history: docs/BACKLOG-ARCHIVE.md#item-gauge-readout-tag-1)

- [ ] (P1, S) **MEASURE-LABEL-PITCH-1 — Measure gives a number an engineer
      will act on and get wrong.** ACCEPTANCE: picking two circular edges
      offers (at minimum) a centre-to-centre reading, labelled as such and
      distinct from the raw minimum-distance reading; edge labels carry enough
      identity (coordinates or a stable name) to reconstruct which entities
      were measured from the readout alone. [src: AUDIT-PRODUCT.md F-7,
      2026-09-16 pass] TERRITORY:
      `apps/web/src/measure/**`, `services/geometry/src/geometry/**` (if centre-to-centre needs a new measurement kind on the wire).
      agentType: frontend-builder (backend-builder if a new measurement kind
      is needed). (history:
      docs/BACKLOG-ARCHIVE.md#item-measure-label-pitch-1)

- [ ] (P1, M) **EDGE-RESOLVE-WARN-1 — a feature needs a warning channel before
      partial/best-effort edge resolution is safe to leave silent.**
      ACCEPTANCE: the evaluator records WHICH tier resolved each subshape
      reference (exact / durable / adjacency-assisted) in the feature's
      rebuild result; the frontend surfaces a visible, dismissable notice
      (tree row + banner, matching the existing `SUBSHAPE_UNRESOLVED`
      vocabulary) when a feature rebuilt on anything less than an exact match,
      naming the feature and the tier. Do not block the rebuild — this is a
      warning channel, not a refusal. [src:
      `docs/design/topological-naming.md` §7.3, `bf05482`, groom pass 26]
      TERRITORY:
      `services/geometry/src/geometry/{features,kernel}/**` (evaluator result), `apps/web/src/routes/PartPage.tsx` (tree row surfacing).
      agentType: kernel-architect + frontend-builder (split into a backend
      slice landing the tier-on-the-wire field, then a frontend slice
      surfacing it). (history:
      docs/BACKLOG-ARCHIVE.md#item-edge-resolve-warn-1)

- [ ] (P3, XS) **INSTANCEOF-THREE-1 — 15 `instanceof` sites against three.js
      classes are latent in the shipped app and will break any new Viewport
      unit test.** ACCEPTANCE: migrate the 15 sites to three's own duck-typed
      flags (`isPerspectiveCamera`, `isOrthographicCamera`, `isMesh`, etc. —
      true across every copy, cost nothing), OR at minimum document the trap
      inline at each site so the first unit-test author does not lose a
      debugging session to it. Grep the CALL (`instanceof `) not a class name
      — `instanceof` against a browser/JS builtin (`HTMLElement`, `Error`,
      etc.) is fine and out of scope. [src: `docs/CLAUDE.md` environment
      recipe, `89d4d4d`+`dbddb17`, groom pass 26] TERRITORY:
      `apps/web/src/viewport/Viewport.tsx`, `SketchScene.tsx`, `BenchBackdrop.tsx`, `glbGeometry.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-instanceof-three-1)

- [ ] (P2, S) **FACE-HOVER-BORE-FLAKE-1 — `face-hover.spec.ts:463` ("the
      addressed BORE wall, small laptop") is intermittent, not a pick-mark
      regression.** ACCEPTANCE: root-cause the 2/6 failure rate (reproduced on
      source predating `9404cb1`, so PICK-PROXY-COLLIDE-1's fix is not
      involved) with the same settle-stamp discipline as `36360ae`/`d0604c5`;
      if it reddens under load and passes after a named settle fix, close
      with that evidence, otherwise state why it is environment-only. [src:
      found while verifying `9404cb1`, filed by backlog-groomer pass 29]
      TERRITORY: `apps/web/e2e/face-hover.spec.ts`. agentType: qa-tester.
      (history: docs/BACKLOG-ARCHIVE.md#item-face-hover-bore-flake-1)

- [ ] (P2, S) **FILLET-GAUGE-FPS-FLOOR-1 — the ">10 frames sampled after
      release" floor assumes ~6.7fps, which headless software GL misses under
      load, and it fails on a clean tree.** ACCEPTANCE: assert the property
      (every sampled frame agrees, however many there are; and separately,
      that at least one frame after release was sampled at all — the "window
      is vacuous" guard, which can stay a small floor since it is a sanity
      check, not a timing budget) rather than an fps-derived count; do not fix
      it by lowering the threshold, which only moves the load level at which
      it flakes. [src: reproduced independently by `357b91e` and `f9fcce6`,
      filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/e2e/fillet-chamfer-gauge.spec.ts`. agentType: qa-tester.
      (history: docs/BACKLOG-ARCHIVE.md#item-fillet-gauge-fps-floor-1)

- [ ] (P2, S) **PATTERN-SCOPE-TIMEOUT-1 — two `pattern-scope.spec.ts` cases
      hit the 60s test timeout under load, on HEAD as well.** ACCEPTANCE:
      instrument before guessing (per-phase timers, not a reflexive
      `expect.poll`/timeout bump) to find which step is slow under load —
      building the plate, drilling, or the pattern dialog itself — and fix or
      budget that step specifically; if the cost is legitimately higher under
      load (e.g. more geometry to rebuild), raise ONLY that step's timeout
      with the measured number stated, not the whole test's. [src: reproduced
      under load on HEAD, filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/e2e/pattern-scope.spec.ts`. agentType: qa-tester.
      ~~**SCRIPT-1**~~ — **CLOSED (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`,
      groom pass 25).** Public Python scripting API shipped; see wave log /
      ROADMAP "Current focus" for the full proof (two-path-identical against a
      browser-driven build, 12/12 facts, byte-equal STEP/STL hashes) and Done
      archive for the record.  ~~**CRAFT-12**~~ — **CLOSED (`7a15bea`, groom
      pass 26).** See wave log above for the fix and the residual it surfaced
      — CRAFT-12-READPROPOSAL-1, filed this pass and closed the same day
      (`5274bea`), see the Ready list below.  ~~**VEC3-DEDUP-1**~~ — **CLOSED
      (`4549da8`, groom pass 26).** One `packages/design/src/vec3.ts` replaces
      the four divergent copies
      (`axisAnchor`/`edgeAnchor`/`faceAnchor`/`gauge.ts`); consolidation chose
      `edgeAnchor`'s picometre-floor + `null`-refusal behaviour and closed a
      live Infinity-into-NaN path (`scale(a, 1/Infinity)` passed every copy's
      own floor guard). 44 e2e green, negative control reddens 9/17 new cases.
      ~~**CRAFT-13**~~ — **CLOSED (`b4e7821`, groom pass 25).** Root-caused:
      the per-segment hit sleeve made band count a function of drag value, so
      a shrinking arc sweep unmounted its own pointer-capture host mid-drag (a
      P0 found in the same investigation, also fixed); the `craft9b-gauges`
      contract-β "intermittent" was the same release-desync shape, confirmed
      as an unstated settle rather than a flake. See wave log for full detail
      and Done archive for the record. (history:
      docs/BACKLOG-ARCHIVE.md#item-pattern-scope-timeout-1)

**Also ready, not yet dispatched (P2, full tickets in the wave log above):**
CRAFT-14 (`ToolButton` disabled-vs-busy audit), CRAFT-15 (3/12 pre-existing
unreachable edge pick points), CRAFT-16 (shell gauge rim-vs-centroid seat,
product decision), CRAFT-17 (`gaugeReach.ts`/`gaugeProbe.ts` DRY convergence),
GAUGE-TOUCH-1 (W3-exit touch QA gate, now covering all nine mounts — still
open, dispatch alongside Phase 5 work per its own note).

**Carried from groom pass 19 — no new P0 that pass; SOLVE-CRASH-1, K2, PBT-1,
CI-BAL, MEASURE-PROXY-1, PICKMARK-OCCLUDE-1, EXPORT-3, REACH-3-FLOW,
REACH-2-FLOW, A11Y-TOOLBTN-1, HEM-1C, HEM-1D, SEL-8 and PGTEST-GATE all
shipped that batch or the last (see Done archive). Nothing is in flight.**
Ranked, disjoint, parallel-dispatchable:

5. **STEPNAME-1 is PART-SHIPPED, and the headline half is NOT ours** Two REAL
      geometry defects found and fixed alongside (non-ASCII names corrupted;
      the file named build123d as its author). See the entry below;
      STEPNAME-1B was the remaining web half and is closed. **STEPNAME-2 is
      closed too (2026-09-04)** — the single-body export carried both of those
      defects on the MORE common path, and now writes through the same owned
      writer, proved byte-identical to build123d's output so no file's shape
      and no golden's hash moved. (history:
      docs/BACKLOG-ARCHIVE.md#item-stepname-1)

6. **ARC-DEGENERATE-1 is SHIPPED** (kernel-architect, 2026-08-29) — 27 of 2000
      payloads were shipping an arc collapsed onto its own centre, at a
      residual of zero; now `sketch_conflicting` with the constraint named.
      See the entry below and ROADMAP for the census and the two follow-ups
      filed.

8. **SNAP-4** (P2, S, frontend-builder) — an explicit Fix on a point the draw
      already grounded misreports OVER-CONSTRAINED.

9. **REACH-2-FLOW-C** (P2, M, frontend-builder) — the feature tree has no
      select-without-editing gesture, and the command band is out of room at
      1280.

**Also ready, not yet dispatched:** QA-R3 (P2, touch — harness gap filed as
PLAYWRIGHT-TOUCH-1), NAME-2b (P2), TITLEBLOCK-STAMP-1 (P2, XS),
SKETCH-COVERAGE-1 (P2), STAGE-DOC-HUNKS-HEADING-1 (P2), SOLVE-CONFLICT-MOVED-1
(P2, XS), SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (P2, S), CHECKUIPARITY-FP-1 (P3),
NUDGE-PLACEMENT-QUANTISE-1 (P3), SOLVER-DOC-1 (P3, XS), SHARD-MANIFEST-CI-1
(P3, new this pass) — see full tickets in place.

**Process/loop-health flag, carried six passes now:**
`docs/GEOMETRY-QA.md`/`docs/UI-REVIEW.md` are stale against the last eight
batches — dispatch `geometry-qa` + `frontend-qa` next batch; the
vision-steward's Sheet metal/Performance/Assemblies/Selection scorecard
re-check is overdue (six passes).  Everything else below is reprioritized but
not yet dispatched this batch.

- [ ] (P2, S) **NAME-2b — the durable-tier re-match NAME-2 shipped resolves
      silently; surface it on `FeatureResult` so an edge-anchored feature can
      show the same `RE-ANCHORED … CONFIRM` chip the drawings module already
      shows for dimensions.** ACCEPTANCE: an edge-anchored fillet/chamfer/edge
      flange that resolves via `resolve_edge_durable`'s tolerant tier shows
      the chip in the tree panel; a strict-tier resolve shows nothing
      (regression guard — no chip noise on the common case). [src:
      `docs/design/topological-naming.md` §13 (`c2700ee`'s own follow-up
      note), filed by backlog-groomer pass 13] TERRITORY:
      `packages/py-kit/src/py_kit/schemas/features.py`, `services/gateway/**` (pass-through), `apps/web/src/routes/ PartPage.tsx`
      / tree panel. agentType: backend-builder + frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-name-2)

- [ ] (P3, XS) **ARC-EXTRUDE-EPS-1 — the kernel's degenerate-arc guard is a
      `<= 0.0` test where the values that reach it straddle zero.**
      ACCEPTANCE: decide where a shared degenerate-curve tolerance lives (a
      neutral module both packages may import, or an explicit reviewed
      kernel->sketch dependency), apply it in `extrude.py` and
      `revolve.py` (which has NO guard at all — a zero-radius arc contributes `_ARC_SAMPLES+1` identical samples at the centre and silently mis-reports the revolve extent),
      with a test at the measured magnitudes rather than at zero. [src:
      ARC-DEGENERATE-1, kernel-architect, 2026-08-29] TERRITORY:
      `services/geometry/src/geometry/kernel/extrude.py`, `revolve.py`, plus
      wherever the shared constant lands. agentType: kernel-architect.
      (history: docs/BACKLOG-ARCHIVE.md#item-arc-extrude-eps-1)

- [ ] (P2, S) **SNAP-4 — an explicit Fix on a point the draw already grounded
      reads as OVER-CONSTRAINED, and the user did not ask for either half.**
      ACCEPTANCE: draw a line from the origin, press `x` on that endpoint, and
      the sketch does NOT report over-constrained; a GENUINE over-constraint
      on the same sketch still does (negative control);
      `constraints.spec.ts`'s conflict case can be moved back onto the origin
      and still recover to `DOF 0 · CONVERGED`. [src: SNAP-3 integration,
      2026-08-16] TERRITORY:
      `apps/web/src/sketch/constraints.ts` (`applyConstraintAction`, the `fixed` branch), `apps/web/src/sketch/store.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-snap-4)

- [ ] (P2, S) **RECT-2 — should DRAWING alone persist a sketch?** ACCEPTANCE:
      a decision recorded in docs/VISION.md or ROADMAP with its reasoning, and
      `userConstrained` either removed or documented as deliberate. [src:
      RECT-1 implementation, 2026-08-16] TERRITORY:
      `apps/web/src/routes/PartPage.tsx`, `apps/web/src/sketch/store.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-rect-2)

- [ ] (P3, XS) **GATE-FLOOR-2 — the two vacuity gaps GATE-FLOOR found that
      gate nothing today, so neither is urgent, but both become live the
      moment somebody wires them in.** It is in neither `just lint` nor CI,
      which is the only reason this is P3. (b) `check-compose.py` has no
      `--self-test` at all; it is honest today only because direct
      `base["documents"]` indexing raises on a missing service, which is a
      property of how it happens to be written rather than a guarantee anybody
      checked. FIX: a count floor on `check-ui-parity`'s literal/operation
      walk, and a `--self-test` for `check-compose` carrying a negative
      control that reproduces a real compose defect. TERRITORY:
      `scripts/check-ui-parity.py`, `scripts/check-compose.py`. agentType:
      platform-builder. (history: docs/BACKLOG-ARCHIVE.md#item-gate-floor-2)

- [ ] (P2, S) **DEP-AUDIT — no dependency-vulnerability gate exists anywhere
      in the repo; a 60-second local `pnpm audit` finds 18 advisories (13
      high).** ACCEPTANCE: dependabot.yml present and valid; CI runs both
      audit commands and surfaces (not blocks) results. [src:
      docs/AUDIT-ENGINEERING.md "Pass 7" M8, filed by backlog-groomer pass 8]
      **ADDENDUM this pass** (`docs/AUDIT-ENGINEERING.md` "Pass 8" N4,
      first-ever Python-side scan): `pip-audit` found **1** advisory,
      `cryptography 49.0.0` (PYSEC-2026-3552, a Bleichenbacher oracle in `pkcs7_decrypt_*`)
      — traced to `moto`'s `joserfc` dependency in the root `dev` group;
      `grep -rn pkcs7` across `services`/`packages` is empty (not called), and
      `uv sync --frozen --no-dev` means it's **absent from every shipped
      image**. Add `pip-audit` to the FIX list alongside `pnpm audit`; also
      add a test asserting `--no-dev` in the image build, since the Python
      answer is currently good only because of an untested Dockerfile flag,
      not because of anything enforced. **STILL UNBUILT, groom pass 11
      (2026-08-24, engineering Pass 9 N10):** `.github/dependabot.yml` still
      absent, no `pnpm audit`/`pip-audit` step in any workflow. TERRITORY:
      `.github/dependabot.yml` (new), `.github/workflows/ci.yml`. agentType:
      platform-builder. (history: docs/BACKLOG-ARCHIVE.md#item-dep-audit)

- [ ] (P2, XS) **SPEC-8 — `materials.spec.ts` silently stops asserting a
      mass-properties claim when its subject disappears.** ACCEPTANCE:
      temporarily rename the testid and confirm the test now FAILS instead of
      passing; revert and confirm green. [src: docs/AUDIT-ENGINEERING.md "Pass
      8" N5, filed by backlog-groomer pass 9] **STILL UNFIXED, groom pass 11
      (2026-08-24, engineering Pass 9 N8d):** both early returns unchanged at
      `:249`/`:267`; re-swept all 126 spec files and confirmed the other four
      early-return sites are TypeScript narrowing after an explicit
      `not.toBeNull()`, not the same escape — the exposure is exactly these
      two lines. TERRITORY: `apps/web/e2e/materials.spec.ts`. agentType:
      frontend-builder. (history: docs/BACKLOG-ARCHIVE.md#item-spec-8)

- [ ] (P2, XS) **AUDITOR-PORTS-1 — the two auditors are told not to
      coordinate, but both default to the SHARED ports (8000-8002, 5173), so
      two audits scheduled close together cost the later one a lost hour
      rebuilding an isolated stack just to get a finding.** ACCEPTANCE:
      `.claude/agents/product-auditor.md` states an isolated-port default,
      pointing at CLAUDE.md's existing recipe; next time both audits land in
      the same window, neither blocks the other. [src:
      docs/AUDIT-ENGINEERING.md "Pass 8" recommendation #8, filed by
      backlog-groomer pass 9] TERRITORY: `.claude/agents/product-auditor.md`.
      agentType: platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-auditor-ports-1)

- [ ] (P2, S) **SHEET-RESCALE-1 — a laid-out sheet's scale cannot be changed
      by anything, so the only way to re-scale a drawing is to start another
      one.** ACCEPTANCE: re-picking Scale on a laid-out four-view sheet
      re-draws every view at the new scale with the title block agreeing; the
      H2 guard still refuses a genuinely divergent PER-VIEW write; an
      orientation flip can then offer the fit its own cell quotes. [src:
      REACH-3-FLOW measurement, filed by frontend-builder 2026-08-28]
      TERRITORY:
      `services/documents/src/documents/drawings.py`, `services/gateway/**`,
      then `apps/web/src/routes/DrawingPage.tsx`. agentType: backend-builder
      (then frontend-builder). (history:
      docs/BACKLOG-ARCHIVE.md#item-sheet-rescale-1)

- [ ] (P2, XS) **TITLEBLOCK-STAMP-1 — the projection-convention symbol
      `5438b73` shipped appears on screen and vanishes from every print.**
      ACCEPTANCE: an exported SVG/PDF/DXF of a first-angle sheet carries the
      1ST-angle cone in its title block; third-angle carries the mirrored
      symbol; the on-screen header cell and the exported stamp never disagree
      (shared derivation, not two). [src: `5438b73` commit message's own
      deviation note, filed by backlog-groomer pass 14] TERRITORY:
      `services/geometry/src/geometry/drawings/` (title block composition).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-titleblock-stamp-1)

- [ ] (P3, S) **NUDGE-PLACEMENT-QUANTISE-1 —
      `nudgePlacement` (`apps/web/src/drawing/authoring.ts`) rounds-then-adds,
      so a coarse press from off-grid skips the value the user is standing
      next to.** ACCEPTANCE: from 12.4713, a coarse press lands on 12.5 (not
      13); a unit test reproduces the round-then-add failure (asserts 13
      today) and reddens against the fixed function; a case confirms the
      direction-of-press semantics (e.g. a downward coarse press from 11 lands
      on 10, not 5, mirroring `steppedDepth`'s own negative-direction case).
      [src: `1661a5b` commit's own deliberately-foreign-territory note, filed
      by backlog-groomer pass 17] TERRITORY:
      `apps/web/src/drawing/authoring.ts` (`nudgePlacement`), its unit test
      file. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-nudge-placement-quantise-1)

- [ ] (P3, S) **CHECKUIPARITY-FP-1 — `scripts/check-ui-parity.py`
      misclassifies the hem-type literals in both directions: `"open"` reads
      AUTHORABLE while `"closed"` — the value the UI actually authors — reads
      RENDER-ONLY.** ACCEPTANCE: re-running the scan against the current web
      corpus classifies `hem_type: "open"` and `hem_type: "closed"` correctly
      (closed reads authorable, since `HemEditor`/equivalent sends it; open
      reads per its actual reachability, not a substring accident); a
      self-test fixture reproduces today's false positive (a corpus file
      containing "open" only inside an unrelated identifier, and "closed" as
      an actual authored literal) and fails against the unfixed matcher. [src:
      found during groom pass 17 while reconciling HEM-1's closure against
      `check-ui-parity.py`'s own reachability claims] TERRITORY:
      `scripts/check-ui-parity.py`. agentType: platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-checkuiparity-fp-1)

## Next (P2)

**Filed groom pass 27 (2026-09-23) — sketch-Fit follow-ups + a DRY/infra
pair:**

- [ ] (P2, S) **VIEWBAR-DRY-1 — the sketch Fit bar duplicates the part view
      bar's instrument-shell styling in `Viewport.tsx` instead of sharing
      `components/ViewBar.tsx`.** ACCEPTANCE: extract the shared SHELL (role,
      chrome attribute, border/background/shadow/flex classes) into one
      primitive both compose, leaving only each bar's own positioning classes
      at the call site; zero visual change (screenshot diff at 1280x800 and a
      small-laptop width); a change to the rail's chrome (border, shadow) now
      requires editing one place. [src: found while reviewing `f9fcce6`,
      re-verified against `5444fa8`, filed by backlog-groomer pass 27]
      TERRITORY:
      `apps/web/src/components/ ViewBar.tsx`, `apps/web/src/viewport/Viewport.tsx`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-viewbar-dry-1)

- [ ] (P2, S) **SKETCH-FIT-GRID-OCCLUDE-1 — a reported dark region near the
      top-left of the sketcher may be hiding grid content; needs
      re-measurement before a fix.** ACCEPTANCE: a frontend-qa or builder pass
      reproduces this LIVE against the running app first (not from the static
      PNG) before scoping a fix; if it does not reproduce, close with the
      measurement that shows so, the same discipline LAYOUT-1 used.
      **RE-CHECKED against the screenshot `5444fa8` refreshed** (same pass,
      moved the Fit bar off the bottom-centre seat) — still no flat block of
      those dimensions found; the referenced image is now stale a second time
      over, so measure against the RUNNING app, not any static PNG in this
      repo. [src: reported, unverified by backlog-groomer pass 27] TERRITORY:
      `apps/web/src/viewport/ SketchScene.tsx` (grid render), `apps/web/src/routes/PartPage.tsx` (feature tree panel).
      agentType: frontend-qa (reproduce) then frontend-builder (fix).
      (history: docs/BACKLOG-ARCHIVE.md#item-sketch-fit-grid-occlude-1)

**Filed groom pass 25 (2026-09-15) — gauntlet + code-review +
DIRECTION-ASSEMBLIES.md findings, ranked by scorecard/correctness impact:**

- [ ] (P2, M) **PERF-REAL-3 — a real part's mesh payload is 142MB, gzip only
      reaches 1.58x.** ACCEPTANCE: mesh quantization (e.g. Draco or a
      fixed-point vertex encoding) measurably shrinks the same fixture's
      payload, stated as a before/after number; per-face-primitive glTF export
      (one primitive per B-rep face) is a named contributor worth checking as
      a separate lever. [src: geometry-qa gauntlet, `docs/GEOMETRY-QA.md`
      2026-09-15] TERRITORY:
      `services/geometry/src/geometry/kernel/tessellate.py` (or wherever GLB is assembled).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-perf-real-3)

- [ ] (P2, S) **NURBS-FIXTURE-1 — acquire a licence-clean foreign NURBS part
      (>1000 faces) to regression-test mesh determinism; this is an
      acquisition problem, not an engineering one.** ACCEPTANCE: find or
      commission a NURBS-heavy STEP part >=1000 faces under a licence this MIT
      project CAN commit (public-domain, CC0, or author permission), add it as
      a committed golden, and confirm it reproduces the pre-fix
      non-determinism when the fix is reverted. [src: geometry-qa gauntlet,
      `docs/GEOMETRY-QA.md` 2026-09-15, F2 follow-up] TERRITORY:
      `services/geometry/goldens/**`. agentType: geometry-qa / founder
      (licensing/acquisition decision). (history:
      docs/BACKLOG-ARCHIVE.md#item-nurbs-fixture-1)

- [ ] (P2, S) **STEP-ROUNDTRIP-COVERAGE-1 — the golden suite has no fixture at
      assembly scale, and a real one shows drift the corpus cannot see.**
      ACCEPTANCE: root-cause the +22 edges (a specific OCCT
      re-tessellation/seam-splitting behaviour, named) and either fix it or
      add a golden at comparable scale with a documented, deliberately looser
      tolerance for large assemblies — do not silently loosen the existing
      1e-7 bound for small parts. [src: geometry-qa gauntlet,
      `docs/GEOMETRY-QA.md` 2026-09-15, Finding 4] TERRITORY:
      `services/geometry/src/geometry/kernel/export.py`, `services/geometry/tests/goldens/**`.
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-step-roundtrip-coverage-1)

- [ ] (P2, S) **GAUGE-QUIESCE-1 — `pattern-gauges.spec.ts`'s 1200ms quiesce
      window is under-margined on both trees.** ACCEPTANCE: raise the window
      with margin against the measured 1.12s tail (state the new value and
      why), or replace the fixed timeout with a condition-based wait on the
      actual settle signal if one exists. [src: CRAFT-13 fix, `b4e7821`,
      2026-09-15] TERRITORY: `apps/web/e2e/pattern-gauges.spec.ts`. agentType:
      qa-tester. (history: docs/BACKLOG-ARCHIVE.md#item-gauge-quiesce-1)

- [ ] (P2, S) **SCOREFRESH-PENDING-1 — `PENDING` on the scorecard freshness
      gate is an unbounded self-granted exemption.** ACCEPTANCE: record the
      sha or date a row was marked PENDING and report STALE once the row's
      territory has moved more than N commits (or M days) since, without
      breaking the existing non-vacuity self-test. [src: code review P1-5,
      `docs/CODE-REVIEW.md`, `451245c`] TERRITORY:
      `scripts/check-scorecard-freshness.py`. agentType: platform-builder.
      (history: docs/BACKLOG-ARCHIVE.md#item-scorefresh-pending-1)

- [ ] (P2, S) **REQUIRED-QUERY-1 — `Operation.required_query` is generated for
      all 86 scripting-API operations and enforced by nothing.** ACCEPTANCE:
      `_send` validates that every operation's declared `required_query` keys
      are present before issuing the request, with a clear client-side error
      naming the missing key(s) rather than a 422 from the server; a
      regression test per operation carrying a required query key. [src: code
      review P2-6, `docs/CODE-REVIEW.md`, `451245c`] TERRITORY:
      `packages/loft-script/src/loft/_operation.py`, `scripts/gen-py-operations.py`.
      agentType: backend-builder.  ~~**CSP-1**~~ — **CLOSED (`ed8c3d7`).**
      `scripts/dist-leg.sh` (`just dist-leg`, e2e.yml's `dist-bundle` job)
      builds the bundle, serves it through the real production nginx config,
      and drives Chromium against it — the missing
      browser-against-the-BUILT-artifact leg this ticket asked for, first.
      Found the proposed `font-src 'self'` CSP was wrong (Vite inlines fonts
      as `data:` URLs, 8 violations, silent fallback- typeface render);
      shipped `font-src 'self' data:`, verified with a positive control (an
      injected inline script both fails to execute and is the only violation
      recorded) plus a second, independently-derived violation count from
      Chromium's own console. TERRITORY:
      `deploy/docker/web/nginx.conf`, `scripts/dist-leg.sh`, `scripts/render-web-nginx.py`, `apps/web/e2e-dist/**`.
      (history: docs/BACKLOG-ARCHIVE.md#item-required-query-1)

- [ ] (P2, L — spike first, S) **PERF-ASM-1 — measure assembly performance at
      realistic instance counts before proposing a fix.** ACCEPTANCE: a
      checked-in perf golden/budget where none existed; a stated, measured
      verdict on whether N=30/N=100 meet a defined "interactive" bar; any
      shipped fix justified by the specific number it responds to, named in
      the commit. [src: vision-steward, `docs/design/DIRECTION-ASSEMBLIES.md`
      §7, 2026-09-15] TERRITORY:
      `services/documents/src/documents/assemblies.py`, `apps/web/src/viewport/AssemblyScene.tsx`.
      agentType: kernel-architect / frontend-builder (split once the number
      names the bottleneck). (history:
      docs/BACKLOG-ARCHIVE.md#item-perf-asm-1)

- [ ] (P2, M) **PICK-ASM-1 — prove MATE-1's occlusion fix at real clutter, not
      the golden's clean two-plate case.** ACCEPTANCE:
      `apps/web/e2e/mate-buried-face-cluttered.spec.ts` proves every occluded
      face in a 3+-instance scene is reachable via the existing (or extended)
      depth-cycling mechanism using a real `page.mouse.click` at the resolved
      screen point — not `force: true` (CLAUDE.md's own standing rule). [src:
      vision-steward, `docs/design/ DIRECTION-ASSEMBLIES.md` §7, 2026-09-15]
      TERRITORY:
      `apps/web/src/viewport/mateDepthStack.ts`, `apps/web/e2e/mate-buried-face-cluttered.spec.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-pick-asm-1)

- [ ] (P2, M) **BOM-ASM-1 — recursive/indented BOM, one level of nesting.**
      ACCEPTANCE: an assembly containing a nested sub-assembly reports the
      CORRECT rolled-up quantity for a part instanced inside it (today's flat
      read undercounts this — verify the undercount reproduces before fixing
      it, then verify it's gone); the flat BOM (no nesting) stays
      byte-identical; contracts regenerated (`just gen-verify` — additive
      field crosses documents→gateway→web). [src: vision-steward,
      `docs/design/ DIRECTION-ASSEMBLIES.md` §7, 2026-09-15] TERRITORY:
      `services/documents/src/documents/assemblies.py`, `packages/contracts`.
      agentType: backend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-bom-asm-1)

- [ ] (P2, M) **FLOW-ASM-1 — an inferred first mate, not a mate-connector
      redesign.** ACCEPTANCE: inserting a second instance next to a first,
      where exactly one obvious face/edge pair matches, offers a one-click
      mate producing the SAME resolved mate a manual pick+pick+submit would;
      an ambiguous scene (two equally plausible pairs) surfaces the choice;
      e2e proves the click-through path end-to-end including the existing
      snap-solve animation. [src: vision-steward,
      `docs/design/DIRECTION-ASSEMBLIES.md` §7, 2026-09-15] TERRITORY:
      `apps/web/src/assembly/**`. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-flow-asm-1)

- [ ] (P1, XS) **TIPRED-1 — `qa-sketch-frame.spec.ts` "a FACE-SEATED sketch's
      origin is selectable and grounds a profile to the face centroid" is RED
      at the branch tip.** ACCEPTANCE: green, with the cause named rather than
      the assertion loosened. agentType: frontend-builder. NB the same sweep
      found `sheet-metal-hem-corner-relief.spec.ts` red on a strict-mode
      collision with `4009042`'s new `data-disabled-reason` spans — already
      fixed upstream by `b9a77c5` and re-verified green here, so it is
      recorded rather than filed. (history:
      docs/BACKLOG-ARCHIVE.md#item-tipred-1)

- [ ] (P3, XS) **FLAKE-SEL4-DRILL-1 — `qa-sel4-verify.spec.ts` "a click on a
      DIFFERENT face does not move the drill point" failed once inside a
      24-case batch and passed 2 of 2 in isolation.** kind: flake. The fixture
      is API-seeded and never enters the sketcher, so it is out of reach of
      both 2026-09-04 viewport changes; recorded so the next sighting has a
      prior rather than starting a fresh hunt. It picks the FIRST raster-order
      lit point that fails a hover probe, which is a silhouette-edge point by
      construction — the same derivation that was making `founder-picking`'s
      face-seat case red, so an interior-point filter is the likely fix.
      agentType: qa-tester.

- [ ] (P2, XS) **SOLVE-CONFLICT-MOVED-1 — a `conflicting` payload can ship
      geometry the solver MOVED, which the DTO promises it never does.**
      Recorded as an executable live limit, bounded both ways. **RE-VERIFIED
      unchanged, groom pass 19 (2026-08-29): SOLVE-CRASH-1 moved the sweep's
      solvable/conflicting census (1327->1328, 276->287) but this finding's
      own count is independent of that reclassification and still reads "2 of
      2000" verbatim in `test_sketch_solver_sweep.py`'s own docstring/test
      comment — no correction needed.** [src: PBT-1 sweep, kernel-architect
      2026-08-29] TERRITORY:
      `services/geometry/src/geometry/sketch/planegcs_solver.py`, `packages/py-kit/src/py_kit/schemas/sketch.py`.
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-solve-conflict-moved-1)

- [ ] (P2, S) **SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 — `status="overconstrained"`
      does not tell a client whether the entities beside it are SOLVED or the
      input returned unchanged, and both happen.** This is why PBT-1's sweep
      excludes `overconstrained` from its solved population — an ambiguity in
      the contract becomes an ambiguity in every gate written against it.
      **RE-VERIFIED unchanged, groom pass 19 (2026-08-29): the overconstrained
      population (282, of which 17 are the input) is untouched by
      SOLVE-CRASH-1's fix — none of the twelve crashing trials were
      overconstrained — confirmed against the current
      `test_sketch_solver_sweep.py` source.** [src: PBT-1 sweep,
      kernel-architect 2026-08-29] TERRITORY:
      `services/geometry/src/geometry/sketch/planegcs_solver.py`, `packages/py-kit/src/py_kit/schemas/sketch.py`.
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-solve-overconstrained-ambiguous-1)

- [ ] (P2, M) **QA-R3 — on touch, four of REACH-1's five new verbs cannot be
      reached at all, because a tablet cannot select two entities.**
      ACCEPTANCE: a touch-native additive gesture (tap-adds while a verb is
      armed, a long-press toggle, or a visible "add to selection" affordance)
      gets two entities selected on a `hasTouch` context, and
      `verb-hint-angle` appears; qualify `scripts/check-ui-parity.py`'s count
      as desktop-only, or count per surface. [src: docs/QA-REVIEW.md
      2026-08-27 QA-R3, filed by qa-tester] **STILL OPEN, groom pass 16 — this
      could only be measured by hand (ad hoc `hasTouch` contexts per-spec),
      because `playwright.config.ts` defines no touch project at all; see
      PLAYWRIGHT-TOUCH-1, filed this pass, for the harness gap this and every
      future touch finding hits.** TERRITORY:
      `apps/web/src/viewport/SketchScene.tsx`, `apps/web/src/sketch/**`, `apps/web/e2e/qa-reach-batch.spec.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-qa-r3)

- [ ] (P2, S) **PLAYWRIGHT-TOUCH-1 — the e2e harness has no touch project, so
      the "touch" half of the QA remit is measured by hand every time.**
      ACCEPTANCE: a `--project=touch` (or equivalent) run exists and is
      documented; at least the existing touch-relevant specs run under it; a
      deliberately broken touch affordance fails the touch project without
      needing a bespoke context in the spec. [src: backlog-groomer pass 16,
      cross-referencing QA-R3's "measured by hand" note] TERRITORY:
      `apps/web/playwright.config.ts`, `apps/web/e2e/*.spec.ts` (consolidation only, no product code).
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-playwright-touch-1)

- [ ] (P2, S) **STAGE-DOC-HUNKS-HEADING-1 — `stage-doc-hunks.py` truncated a
      BACKLOG entry again, this time on a heading-immediately-followed-by-
      list-item boundary its own fixtures cannot reach.** ACCEPTANCE: a
      `--self-test` fixture reproduces this exact shape (a `###`/bold heading
      immediately followed by a `- **ID**` list-item body, both added in one
      hunk, one marker on the heading line) and demands the heading+body stage
      together; the existing three fixtures (plain BACKLOG list items,
      bold-lead ROADMAP paragraphs, bold-continuation) are unaffected; the
      cross-check's negative control still refuses on a deliberately-reverted
      boundary rule. [src: PANEL-DENSITY-1 agent report, 2026-08-28,
      reproduced via `git show :docs/BACKLOG.md` after the fact] TERRITORY:
      `scripts/stage-doc-hunks.py`. agentType: platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-stage-doc-hunks-heading-1)

- [ ] (P2, S) **SKETCH-COVERAGE-1 — `equal` and `tangent` constraints have no
      e2e driving them through the UI; they are reachable but nothing proves
      it.** ACCEPTANCE: one e2e case per verb, authoring it through the real
      UI (not a fixture pre-loaded with the constraint), asserting the solved
      result changes as expected and the constraint round-trips through
      save/reload; if either verb turns out to be genuinely unreachable,
      re-file as a P1 capability gap instead. [src: backlog-groomer pass 15,
      cross-referencing SKETCH-VOCAB-1's closure] TERRITORY:
      `apps/web/e2e/` (new spec cases), `apps/web/src/sketch/**` if a real gap
      is found. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-sketch-coverage-1)

- [ ] (P3, XS) **SOLVER-DOC-1 — `solver.py`'s docstring claims the null space
      "stays anchored at the seed," and measurement says otherwise.**
      ACCEPTANCE: the docstring's claim matches `1ae3270`'s measurement; no
      behaviour change. [src: `1ae3270` commit investigation, filed by
      backlog-groomer pass 15] TERRITORY:
      `services/geometry/src/geometry/assembly/solver.py` (docstring only).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-solver-doc-1)

- [ ] (P2, S) **FLOW-POLISH-1 — four small flow-capture defects from the
      fourth product-audit pass, bucketed to keep the board a workable size.**
      Symmetric wanting points, not edges) gives no way to tell what was
      actually picked without screenshotting the viewport (T-6); circular-edge
      aria-labels report the CENTRE MINUS THE RADIUS, not the centre (T-12:
      four holes at the provably symmetric ±23.5,±23.5 are labelled at the
      asymmetric -26.7 and +20.3 — reads as a modelling error in a part that
      is correct). [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-24 (fourth pass)"
      T-2/T-4/T-6/T-12, filed by backlog-groomer pass 11] TERRITORY: varies —
      auth error rendering (T-2), sketch drag-draw focus (T-4), selection
      readout (T-6), edge-pick aria-label generation (T-12), all
      `apps/web/**`. agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-flow-polish-1)

- [ ] (P2, M) **IMPORT-HEAL-1 — a STEP import yielding zero solids has no
      recovery path.** ACCEPTANCE: a golden fixture with a small controlled
      defect (e.g. one face split by a hairline slit) imports successfully
      post-fix where it failed pre-fix; a genuinely unrecoverable fixture (no
      closed volume possible) still returns `import_no_solid` unchanged —
      negative control. [src: AUDIT-PRODUCT.md F-6.1, ranked #6, 2026-08-17
      pass] TERRITORY:
      `services/geometry/src/geometry/kernel/imports.py`, `services/geometry/src/geometry/kernel/_step_parse_worker.py`.
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-import-heal-1)

- [ ] (P2, S) **IMPORT-HEAL-2 — surface the healing report / partial-result
      honesty in the import UI.** ACCEPTANCE: when the import response carries
      `repaired: true`, the import UI shows an honest notice naming what was
      repaired rather than a silent success. [src: AUDIT-PRODUCT.md F-6.1,
      2026-08-17 pass] TERRITORY:
      `apps/web` (the existing STEP-import flow, `CreateStrip`'s Import button).
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-import-heal-2)

- [ ] (P2, XS) **EXPORT-ERR — an unsupported export format returns a raw
      pydantic `literal_error` instead of a typed
      `export_format_unsupported`.** ACCEPTANCE: a typed error naming the
      supported-formats list, using `py-kit`'s existing error envelope,
      replaces the raw pydantic error on both export enums
      (`ExportFormat`, `ArtifactFormat`); test asserts the error `type` and a
      `supported` field. [src: AUDIT-PRODUCT.md F-7, 2026-08-17 pass]
      TERRITORY:
      `packages/py-kit/src/py_kit` (error envelope), `services/gateway/src/gateway/features.py`
      or the geometry export route. agentType: backend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-export-err)

- [ ] (P2, XS) **SOLVE-2 — the feature-tree panel's SOLVE cell and the sketch
      DRO's SOLVE cell can read `Solved` and `DOF 6 · UNDER-CONSTRAINED`
      simultaneously, on the same screen, for the same sketch.** ACCEPTANCE:
      the two cells no longer present contradictory verdicts for the same
      sketch state; unit test on the tree cell's label given an
      under-constrained-but-converged sketch. [src: docs/AUDIT-PRODUCT.md
      "Pass 2026-08-21" R-3, filed by backlog-groomer pass 8] TERRITORY:
      `apps/web/src/routes/PartPage.tsx` (feature-tree SOLVE cell). agentType:
      frontend-builder. (history: docs/BACKLOG-ARCHIVE.md#item-solve-2)

- [ ] (P2, M) **REACH-2-FLOW-C — the feature tree has no gesture that selects
      WITHOUT entering a command, and the band is out of room at 1280.**
      ACCEPTANCE: (1) a tree row can be selected without opening its editor,
      and editing is reachable by at least two visible gestures; (2) holding a
      scope at 1280x800 no longer costs EXPORT its labels. [src: REACH-2-FLOW
      build, 2026-08-28, frontend-builder] TERRITORY:
      `apps/web/src/components/FeatureTreePanel.tsx`, `apps/web/src/routes/PartPage.tsx`, `packages/design/src/primitives/ CommandBand.tsx`, `apps/web/e2e/**`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-reach-2-flow-c)

- [ ] (P1, XS) **STEPNAME-1 — assembly STEP export names components with raw
      UUIDs instead of their part names.** ACCEPTANCE: exporting the audit's
      two-part assembly and reading it back names both components by their
      part name, not a UUID; new golden/assertion on the STEP writer.
      **GEOMETRY HALF SHIPPED (kernel-architect, 2026-08-29); THE HEADLINE
      HALF IS NOT A GEOMETRY DEFECT.** The writer has threaded the instance
      name into the NAUO and the PRODUCT since
      `0d3ea59` (2026-07-31, three weeks BEFORE the audit) — asserted on the
      emitted bytes, not assumed. The UUID the audit read is the documented
      FALLBACK for a request with no `name`, and the caller that omits it is
      `apps/web/src/assembly/evaluateRequest.ts`, which builds
      `EvaluateAssemblyRequest` without the field the DTO has carried all
      along. That is a one-line web change in foreign territory: STEPNAME-1B.
      What WAS wrong here, found by exercising the writer rather than reading
      it, and both fixed: (a) **every non-ASCII name was corrupted** —
      `TCollection_ExtendedString(str)` binds the `isMultiByte=False` overload
      and walks UTF-8 bytes as characters, so "Flänsch" measured 17 characters
      instead of 13 and reached the file double-encoded; (b) the originating
      system read `build123d`, so a file Loft authored named a library
      instead. Note (a) is why fixing the web alone would have been wrong: a
      name that is present and corrupted is not better than one that is absent
      and obvious. Duplicate part names DECIDED and pinned: two instances of
      one part correctly share one PRODUCT (the case that occurs); two
      DIFFERENT parts a user names alike keep the name verbatim and collide on
      `PRODUCT.id`, which we do not disambiguate because that means mangling a
      part number in the file a supplier quotes from. Two mutants, both
      restored: reverting the encoding reddens 8 cases (all and only the
      non-ASCII ones, on both `BodyShape` members); reverting the originating
      system reddens 1. Filed alongside: STEPNAME-1B (web), STEPNAME-2
      (single-body path), STEPDET-1 (a determinism hole found by writing the
      test). Gates: `just lint` exit 0, `uv run pyright` clean, 482
      STEP-adjacent tests green. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21
      (second pass today)" S-22, filed by backlog-groomer pass 9] TERRITORY:
      `services/geometry/src/geometry/kernel/` STEP export path (assembly
      writer). agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-stepname-1-2)

- [ ] (P3, XS) **STEPHDR-1 — a non-ASCII document name reaches the part-21
      HEADER as raw UTF-8 rather than the standard's `\X2\` escapes.**
      ACCEPTANCE: encode the header name per part 21
      (`\X2\<utf-16be hex>\X0\`) and assert on the emitted bytes that a strict
      ISO-8859-1 read recovers the name, for the same seven mangling shapes
      the two naming suites already share. Watch the ASCII case stays
      byte-identical, or every existing digest moves for a name that needed no
      escaping. [src: STEPNAME-2, kernel-architect, 2026-09-04] TERRITORY:
      `services/geometry/src/geometry/kernel/export.py` (`_write_step_document`).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-stephdr-1)

- [ ] (P2/P3, S) **SM-POLISH-1 — remaining sheet-metal/assembly polish from
      the fabrication-handoff audit, bucketed rather than individually
      ticketed to keep the board a workable size.** [src:
      docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)", filed as a
      bucket by backlog-groomer pass 9] **ADDED, groom pass 11 (2026-08-24),
      same bucket shape — pull by id, re-derive acceptance from the finding:**
      **P1** — after a failed rebuild, fit the view and clamp/hide pick
      proxies that render off the visible frame (T-9: three of four
      repair-mode edge proxies measured at y=-186, y=1017, x=-4 on a
      1000px-tall window; the camera is also left at the sketch-edit
      orientation rather than refit). **P2** — Measure's circle-to-circle
      reading is not centre-to-centre and doesn't say what it measured (T-14,
      corroborates S-33: two Ø6.6 holes 47mm apart in both axes read
      `DISTANCE 70.9597mm`, which is neither the 47mm nor the 66.468mm
      diagonal); drawing dimensions have no tolerance field at all and print
      trailing zeros (`Ø25.000`) — T-17, corroborates/extends S-35; no centre
      marks, centrelines, or hole table on drawing views (T-17);
      orientation-button glyphs are still only a 1.4px dot apart at 24px
      render size — T-19 corroborates S-30, "half closed" (a per-facet dot now
      exists, still illegible). **P3** — creating a DRAWING also fails to open
      it (T-25 extends S-17's assembly finding to a third creation flow —
      three flows, two behaviours); duplicate `Centroid`/`Centre of mass` rows
      carrying the same number, no inertia tensor, and stray tooltips left
      painted in the viewport after the cursor moved (T-24). [src:
      docs/AUDIT-PRODUCT.md "Pass 2026-08-24" fourth/fifth passes
      T-9/T-14/T-17/T-19/T-24/T-25, added by backlog-groomer pass 11]
      TERRITORY: varies per item — see the cited finding. agentType: varies
      (mostly frontend-builder; S-37's import recognition is
      kernel-architect). (history: docs/BACKLOG-ARCHIVE.md#item-sm-polish-1)

- [ ] (P2, S) **GQA-1 — the invariant triple tier 4a compares (outer area,
      perimeter, in-plane centroid) is NOT a fingerprint of the outer wire;
      §12b overclaims "the same outer wire, to tolerance."** ACCEPTANCE:
      §12b's sentence corrected; either a new invariant closes the
      transition-bracket case (new golden) or the honest-limit is formally
      documented with a gated characterization test if closing it is deferred
      again. Mutation check:
      `test_faces_geom3_qa.py::test_the_outer_invariant_TRIPLE_is_NOT_a_ fingerprint_of_the_outer_wire`
      already gates the KNOWN-limit characterization — goes red the day a
      shape-sensitive invariant is added, which is the acceptance signal for a
      real fix. [src: geometry-qa independent verification of GEOM-3,
      `0628ceb`, 2026-08-16, docs/GEOMETRY-QA.md "GQA-1"] TERRITORY:
      `docs/design/topological-naming.md` §12b (doc fix, cheap, do first),
      `packages/py-kit` (`PlanarFaceSignature`, if a new invariant is added), `services/geometry/src/geometry/kernel/faces.py` (tier 4a/4b),
      geometry goldens. agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-gqa-1)

- [ ] (P2, S) **SKETCH-3 — reserved-id hydration guard: an externally-authored
      entity named `origin`/`x-axis`/`y-axis` would silently BECOME the sketch
      frame.** ACCEPTANCE: a hydration test that constructs a sketch with a
      user entity literally named `origin` and asserts the frame is NOT
      silently replaced (exact behaviour — reject vs. remap — is a product
      decision to make when this is picked up, not implied by this ticket).
      [src: SKETCH-2 builder, flagged not built, relayed by groomer
      2026-08-15] TERRITORY: `apps/web/src/sketch/datum.ts`, sketch
      persistence/hydration path. agentType: frontend-builder. Gate on Phase 5
      scripting surface landing; do not build ahead of the exposure that makes
      it real. (history: docs/BACKLOG-ARCHIVE.md#item-sketch-3)

- [ ] (P1, XS) **FB-19b — FB-19 shipped (`f7c41d9`) but is not DONE:
      unreviewed, unQA'd, and the founder has not seen the before/after
      screenshots.** ACCEPTANCE: (1) run `fb19-chrome-density.spec.ts`,
      root-cause and fix if red; (2) `code-reviewer` + `qa-tester` sign off;
      (3) orchestrator SENDS `docs/screenshots/fb19-*` to the founder in chat
      per CLAUDE.md's design mandate ("surfaced" = sent, not merely generated)
      — this last step is not a build task, flag it for the orchestrator
      rather than a builder. [src: FB-19 provenance note, groomed 2026-08-15]
      TERRITORY: read-only verification;
      `apps/web/e2e/ fb19-chrome-density.spec.ts` only if it needs a fix.
      agentType: frontend-builder or qa-tester. (history:
      docs/BACKLOG-ARCHIVE.md#item-fb-19)

- [ ] (P2, XS) **ESC-3 — the one scenario where c449235's Escape-disarm rung
      actually prevents an exit (armed Dimension in an EMPTY sketch) is
      covered by no test, unit or e2e.** FIX: add a test that arms Dimension
      in an EMPTY sketch and asserts Escape disarms without exiting; keep the
      4-entity test as a secondary regression, not the only one. Mutation
      check: reverting the disarm rung reddens the NEW empty-sketch test.
      [src: code review of c449235, orchestrator dispatch 2026-08-14]
      TERRITORY: `apps/web/src/sketch/store.test.ts`. agentType:
      frontend-builder. (history: docs/BACKLOG-ARCHIVE.md#item-esc-3)

- [ ] (P2, S) **VP-1b — orbit-while-sketching is undiscoverable; neither
      VP-1's MIDDLE button nor VP-1a's Alt+drag is announced anywhere in the
      sketcher.** ACCEPTANCE: entering sketch draw mode shows a cue naming
      both bindings; test asserts the cue text differs from the non-sketch
      `viewNav` cue. [src: VP-1a follow-up noted 2026-08-14, filed this pass]
      TERRITORY:
      `apps/web/src/components/NavCue.tsx`, `apps/web/src/viewport/**` (wiring).
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-vp-1)

- [ ] (P2, XS) **QA7-1b — the static gate QA7-1 shipped (`db144d7`) recognises
      a SOLVE-cell subject only via the literal `"eval-status"` string or a
      `const <name> = page.getByTestId("eval-status")` binding, so
      `page.locator("[data-testid=eval-status]")` or `const cell = status`
      slip past it undetected.** ACCEPTANCE: the two measured-slip shapes now
      fail the gate when they name a string outside `solveSummary`'s
      vocabulary; the non-vacuity negative control (the shipped pre-fix defect
      line, asserted before the subject) still passes. [src: code review of
      QA7-1 (`07c4005`), amber follow-up, filed 2026-08-15] TERRITORY:
      `apps/web/e2e/qa-sel7-verify.spec.ts` (scanner function), or a new
      `scripts/` gate if promoted repo-wide. agentType: frontend-builder.
      (history: docs/BACKLOG-ARCHIVE.md#item-qa7-1)

- [ ] (P2, S) **TOUCH-1 — there is no touch/mobile Playwright PROJECT, and has
      never been one since `playwright.config.ts` was introduced; QA briefs
      that say "desktop AND touch" have been silently half-satisfied for the
      life of the e2e suite.** ACCEPTANCE: a touch project exists and runs in
      CI; at least the 6 specs above (already touch-aware) run under it rather
      than only under per-spec overrides; document in this file's own
      convention (or CLAUDE.md) what "desktop and touch" verification means
      going forward so future briefs stop overclaiming coverage that isn't
      there. [src: QA finding, relayed 2026-08-15 — process gap, not a single
      bug] TERRITORY:
      `apps/web/playwright.config.ts`, `.github/workflows/e2e.yml`. agentType:
      platform-builder or frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-touch-1)

- [ ] (P2, S) **TOUCH-2 — the sketch origin/frame grab disc is well under any
      touch-target guideline: 9 px at the default camera, 4 px zoomed out 32
      notches.** ACCEPTANCE: a touch-emulated pick (once TOUCH-1's project
      exists) hits the origin/axis at >=24 px from centre at the default
      camera; a unit test on the hit-region math independent of a touch
      harness in the meantime. [src: independent QA of SKETCH-2,
      `docs/ UI-REVIEW.md`, 2026-08-15] TERRITORY:
      `apps/web/src/sketch/datum.ts`, `apps/web/src/sketch/ origin.ts`.
      agentType: frontend-builder. Natural pairing with TOUCH-1; does not
      require it to ship first (the hit-region fix is independent of whether
      CI runs a touch project). (history:
      docs/BACKLOG-ARCHIVE.md#item-touch-2)

- [ ] (P2, XS) **QA-SK2-3 — "Finish sketch" silently drops a click landing
      during a live save, 2 in 10 under load.** ACCEPTANCE: a spec that
      triggers a save-in-flight and clicks Finish during it asserts the sketch
      exits (not silently ignored); reproduces the 2-in-10 rate before the
      fix, 0-in-N after over a comparable number of trials. [src: independent
      QA of SKETCH-2, `docs/UI-REVIEW.md` QA-SK2-3, 2026-08-15] TERRITORY:
      `apps/web/src/components/SketchStrip.tsx` (or equivalent), `apps/web/src/sketch/store.ts` (`finishSketch`).
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-qa-sk2-3)

- [ ] (P2, S) **SPEC-6 — `measureReach` in `pick-affordance.spec.ts` reads
      `data-edge-pick-hover` with the same zero-settle pattern SPEC-5 found
      and fixed for the hole scan's `data-hole-point-hover` — filed, not
      fixed, and possibly already covered.** ACCEPTANCE (if not already
      covered): apply the same oracle pattern to `measureReach`'s attribute
      read; re-measure the currently-green reach thresholds this call site
      feeds (fillet/measure/mate specs) and confirm they don't move, or update
      them with the corrected (smaller) measured reach if they do. [src:
      ROADMAP CI-4 substrate pass, `8d5be24`/`c7d3f2a`, relayed 2026-08-15]
      TERRITORY: `apps/web/e2e/pick-affordance.spec.ts` (`measureReach`).
      agentType: frontend-builder. DO NOT dispatch concurrently with any other
      agent already in this file — check git log / ask the orchestrator first.
      (history: docs/BACKLOG-ARCHIVE.md#item-spec-6)

- [ ] (P3, XS) **SPEC-7 — one observation, not a diagnosis:
      `pick-affordance.spec.ts:780` ("SEL-6 — the default face hover sees past a hidden body too")
      failed once on CI at `8d5be24`, with both immediate descendant commits
      green.** If still unexplained after that check: re-run the test under
      load a handful of times and see whether it reproduces before spending
      more on it; one CI sample with two green descendants is not yet evidence
      of a standing defect. [src: orchestrator CI observation, relayed
      2026-08-15] TERRITORY: `apps/web/e2e/pick-affordance.spec.ts`.
      agentType: frontend-builder or qa-tester (reproduction first, before any
      fix). (history: docs/BACKLOG-ARCHIVE.md#item-spec-7)

- [ ] (P2, XS) **CONTRACT-1 — `SolvedDimension.value_mm`'s OpenAPI docstring
      still describes pre-SOLVE-1 semantics, and `gen-check` cannot see it
      because it regenerates from the same wrong docstring.** ACCEPTANCE:
      `just gen` regenerates contracts with the corrected description;
      `packages/ts-client` reflects it. [src: docs/AUDIT-ENGINEERING.md "Pass
      9" N3, filed by backlog-groomer pass 11] TERRITORY:
      `packages/py-kit/src/py_kit/schemas/sketch.py`. agentType:
      kernel-architect (schema owner) or backend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-contract-1)

- [ ] (P2, S) **SEC-TEST-1 — no negative control proves the gateway ignores a
      client-supplied principal header.** ACCEPTANCE: both tests pass today
      and fail under a mutation that merges client headers into the upstream
      set. [src: docs/AUDIT-ENGINEERING.md "Pass 9" N6, filed by
      backlog-groomer pass 11] TERRITORY:
      `services/gateway/tests/test_upstream.py` or similar (new). agentType:
      backend-builder. (history: docs/BACKLOG-ARCHIVE.md#item-sec-test-1)

- [ ] (P2, S) **K3 — no automated licence gate over the ~1,036-package npm
      tree; `check-licences.py` covers the Python environment only**
      `docs/LICENSING.md` §5's JS table (78 prod packages, all
      MIT/Apache/ISC/OFL/BSD/Unlicense) was produced by a human running
      `pnpm licenses list` once on 2026-07-31; a GPL npm package added
      tomorrow fails no gate anywhere. Given this repo's P0 licence incident
      (LIC-1) was caused by exactly this — trusting a one-time human read of
      dependency metadata — close the asymmetry:
      `pnpm licenses list --prod --json` piped through an allowlist, ~15
      lines, in the `licences` CI job beside the Python profile. [src:
      engineering-auditor pass 5, 2026-08-14 (K3)] (history:
      docs/BACKLOG-ARCHIVE.md#item-p2-s-k3-no-automated-licenc)

- [ ] (P3, XS) **K6-tail — derive `docs/ROADMAP.md`'s "Current focus" line
      instead of hand-writing it; this is the THIRD time an audit has found it
      stale (H6 2026-07-25, J13 2026-07-30, K6 2026-08-14).** Fixed by hand
      again this pass. Recommend a machine-written line (newest non-docs-only
      commit's ticket prefix, or a `docs/.last-sweep` record) so it cannot
      drift between grooms. Low priority precisely because it costs nothing to
      keep fixing by hand each pass — but three recurrences says the field
      itself is the bug. [src: engineering-auditor pass 5, 2026-08-14 (K6)]

- [ ] (P2, S) **K8 — three of the last five commits landed with no independent
      code review and no QA pass, disclosed only in the commit message, not in
      ROADMAP or BACKLOG** Convention going forward: an `(UNREVIEWED)` suffix
      on the BACKLOG line (now applied to FB-20/CI-3 in the archive above)
      until code-reviewer + qa-tester have independently passed it. Also
      noted: BACKLOG had exactly one `CLOSED-PENDING-QA` marker while RETRO
      §6.5 said "several" — fix whichever is wrong when next touching RETRO.
      [src: engineering-auditor pass 5, 2026-08-14 (K8)] (history:
      docs/BACKLOG-ARCHIVE.md#item-p2-s-k8-three-of-the-last-f)

- [ ] (P2, XS) **REV-1(c) — `qa-harness.spec.ts:730` asserts a tautology:
      `/achieved 0 render\(s\)/` can only fire when `observed < 1`, so the
      match is guaranteed by construction after a non-throwing call. Same at
      :704-706 for three other asserted values.** Sub-items (a)(b)(d)(e)(f)(g)
      of the original REV-1 are CLOSED — see `docs/ROADMAP.md`'s 2026-08-14
      entries for the measurements. Only (c) remains: replace the tautological
      regex assertions with a check that could actually fail (e.g. assert the
      SPECIFIC render count, not merely "not zero"). [src: ultracode review
      2026-08-13; groomer-compacted 2026-08-14]

- [ ] (P2, XS) **REV-2 — the retries posture guard stops covering a renamed
      Playwright config, silently** Not higher priority because
      `--fail-on-flaky` remains a genuine independent backstop: a retry that
      actually FIRES still reddens the reconcile job. It is the posture CLAIM
      that is falsifiable-in-name-only. FIX (3 lines, before the greps):
      assert each file the guard enumerates exists, and fail naming it when it
      does not. [src: ultracode review, 2026-08-13] (history:
      docs/BACKLOG-ARCHIVE.md#item-rev-2)

- [ ] (P2, S) **REV-5 — the two instruments that could close the
      stale-readback and context-loss exposures are exercised only by
      themselves** Wiring it up needs a different shape, not a flag flip. (b)
      `qa-harness.spec.ts:756` asserts `glEvents` is EMPTY, i.e. that the
      `webglcontextrestored` path was never taken — so the `invalidate()` fix
      at `Viewport.tsx:505`, sold as a real product fix, is exercised by
      nothing. `WEBGL_lose_context` is available in headless Chromium, so the
      mutation is cheap: lose, restore, assert the scene repaints with no user
      input, and assert it FAILS with the `invalidate()` removed. [src:
      ultracode review, 2026-08-13] (history:
      docs/BACKLOG-ARCHIVE.md#item-rev-5)

- [ ] (P3, S) **CI-4 — standing umbrella for e2e-suite instability under
      runner load. ORIGINAL QUESTION ANSWERED 2026-08-29 (qa-tester, eleven
      full-shard + 17 targeted runs): NO, the suite is not systemically
      unstable — shard 3/4 was structurally overloaded (Playwright cuts whole
      files in filesystem order on equal test COUNT, and the heaviest specs
      share alphabetically-adjacent prefixes), measured at 1.58x the median
      wall.** Kept open as a standing umbrella for the next unexplained
      shard-3/4 red, not as an active fire. Full incident history (the
      original three-mechanism diagnosis, the substrate pass, the four
      separately-fixed causes): see `docs/CHANGELOG.md`'s CI-4 sections and
      this Done archive. [src: orchestrator CI root-cause, 2026-08-11;
      qa-tester CI-4 pass, 2026-08-29] (history:
      docs/BACKLOG-ARCHIVE.md#item-ci-4)

**VERIFIED ON THE REAL CI RUNNER, groom pass 19 (corrects the local-box figure
this ticket originally shipped with): per-shard walls 1425/1337/1550/ 1360s, a
1.16x spread (down from 1.58x), 25.8 min critical path, step-cap headroom
1.55x (not the 2.1x first computed from a local-box run — the duration
manifest was measured on this container and CI's relative per-file costs
differ). Follow-up: SHARD-MANIFEST-CI-1 (P3, below) — seed the manifest from
CI's own reports.** Local-box validation (kept for the GATE-1 coverage proof,
which does not depend on absolute timings): a real four-shard run measured
1132/1085/1138/1116s, 686/686 expected, 0 flaky, a 1.05x spread; GATE-1 (an
unmeasured file is still assigned, weighted heaviest) proven live with a
throwaway spec; `--drift`'s destructive-advice footgun on a partial report set
found and closed (`--allow-shrink`). [src: platform-builder, 2026-08-29;
measurement in docs/QA-REVIEW.md CI-4]

- [ ] (P0, L) **FB-8 — "too many [points] to see what you are clicking"; wants
      Fusion/Plasticity pre-selection** — a snapping pointer, the FACE (not
      the body) highlighting under the cursor, and a small axis showing
      direction. `ModelMesh.tsx:37` types highlight as per-BODY
      (`"none" | "hover" | "selected" | "feature"`), so hovering glows the
      whole solid. This is the root of FB-2/FB-3 as EXPERIENCED: a mis-aim is
      invisible instead of visible and free. The hovered-face normal also
      pre-empts FB-4 — you would see which way "out" points before authoring.
      Spec IN FLIGHT (vision-steward).

- [ ] (P1, L) **FB-18 — a 50x mirror/rotate never finished; it "errored and
      stopped".** Note K8s does NOT solve this and adding it would not have
      helped: an HPA adds replicas for THROUGHPUT and cannot speed up one
      in-flight request, CPU limits throttle rather than scale, and vertical
      scaling is capped because OCP does not release the GIL (measured: one
      geometry worker uses ~1.1 cores whatever the box has, docs/PERF.md
      §CONCURRENCY). Acceptance: the 50x case named as a benchmark with its
      measured cost and where the time goes, then the fix that measurement
      implies. [src: founder 2026-08-01] (history:
      docs/BACKLOG-ARCHIVE.md#item-fb-18)

- [ ] (P0, L) **FLOW-1 (was FB-20 — renumbered 2026-08-14, id collided with
      the camera-stolen-after-extrude fix also called FB-20, `d091112`; see
      the archive) — the FLOW from sketch to feature, and the parts page, both
      need an overhaul.** This item stays open as the umbrella/parts-page
      tracker; treat the slices as the actual buildable work. **CORROBORATED,
      groom pass 11 (2026-08-24, T-23): a full DOM sweep for
      `[data-testid*="handle|gizmo|drag|arrow|manip"]` returns `[]` — the
      mandate's own named "biggest gap," M5, is still at exactly zero, not
      partially shipped. Extrude is a numeric field with a live coloured
      preview and no draggable arrow; nothing proposes the next verb after a
      solved sketch beyond pre-selecting the profile.** [src: docs/
      AUDIT-PRODUCT.md "Pass 2026-08-24 (fifth pass)" T-23] [src: founder
      2026-08-01] (history: docs/BACKLOG-ARCHIVE.md#item-flow-1)

- [ ] (P1, L) **QA3-2 — a sketch on an imported face has NO reference to the
      import, and its origin is the face's area centroid** [docs/QA-REVIEW.md
      2026-08-01 QA3-2] PARTIAL 2026-08-02 (FB-22): the origin half is DONE —
      the sketch frame's zero is drawn, snappable, and named per plane kind,
      so a face-seated sketch's origin now says "Face centre" and that it
      moves. What remains is the projection half: body edges/hole centres
      projected into the sketch, snappable and dimensionable. (history:
      docs/BACKLOG-ARCHIVE.md#item-qa3-2)

- [ ] (P1, M) **SEL-1 — default hover lights the whole body; a working
      engineer needs the FACE** **STATUS 2026-08-06 (code review) — A1 /
      A2(face) / A7 shipped; the item is NOT complete.** An earlier note here
      said it was, which the unticked box already contradicted. What remains,
      and is now SEL-4: the armed EDGE and shell/draft picks (fillet, chamfer,
      shell, draft) still hang their only hit-test on a 24 px `PickNode`, so
      the reachability floor A2 measured for faces is untouched on them; and
      A2's stated acceptance names a dense-hole-pattern fixture, where the
      shipped gate uses a six-face box. Two review findings fixed in the same
      pass: A7's recession was GLOBAL, so it dimmed the aim affordance on the
      five overlays A2 never converted (it is now opt-in per surface, and 50 %
      was under the WCAG 1.4.11 non-text floor at 2.98:1 — 60 % measures
      3.86:1); and the addressed face's traced boundary drew with no depth
      test, so a bore's far circle painted a bright ellipse across the outside
      of the plate. [src: founder] (history:
      docs/BACKLOG-ARCHIVE.md#item-sel-1)

- [ ] (P1, M) **DRAG-1 — hovered-face normal arrow, doubling as the
      extrude/cut direction control** Direct fix for "a cut misses everything
      going a different way." Acceptance A5/A6. [src: founder] NOTE
      2026-08-14: id renamed from a stale SEL-4 collision (SEL-4 now names the
      shipped edge/shell/draft pick fix). This is a DIRECTION control
      (forward/reverse arrow), not the draggable-DISTANCE handle the founder's
      #1 gap (M5, product-audit 2026-08-14) asks for — both are needed; M5 is
      the bigger one and is unclaimed. (history:
      docs/BACKLOG-ARCHIVE.md#item-drag-1)

- [ ] (P3, S) **CONC-8 — editing a dimension under a picked-edge fillet fails
      `subshape_unresolved` on a 0.01 mm change** Fresh product-audit pass
      (2026-07-23) reframes assemblies as **"a one-way street"** — buildable
      and solvable, but no export, no collision check, no import — that gap
      now leads the queue (P0/P1). **Section views v1 SHIPPED**
      (kernel-architect, 2026-07-23): single planar full section of a
      single-body part by principal / axis-aligned-offset datum reference —
      `drawings/section.py` half-space cut + coplanar loops +
      `ComposedHatch` (ANSI-45° even-odd scanline clip) across SVG/PDF/DXF,
      `views.section_params jsonb` (0008); wrong-half + multi-loop +
      byte-determinism goldens; oblique + the `project_view` frame refactor
      are v2/§11. Spike de-collected. (history:
      docs/BACKLOG-ARCHIVE.md#item-conc-8)

- [ ] (P2, M) Drawings parity #4 — assembly drawing views + BOM/balloons
      (WIRE). The real capability behind the D4 gate: compose a drawing view
      that projects an ASSEMBLY (not a single part) — an assembly-side
      evaluation-request / compose branch, plus BOM table + balloon
      authoring/compose. The `assembly_views_unsupported` gate in
      `gateway/drawings.py` is REMOVED (slice 2). Supervised M feature (kernel
      + gateway + documents + web). [src: AUDIT-ENGINEERING.md D4 follow-on] -
      [x] SLICE 1 (geometry projection core):
      `evaluate_assembly_drawing_views` (`geometry/drawings/assembly_project.py`)
      — `solve_assembly` (reused verbatim) → `place_body` each instance at its
      solved world pose → compose ONE `Compound` → the SAME exact HLR
      `project_view` per view. Sibling DTOs
      `EvaluateAssemblyDrawingViewsRequest`/`Result` (reuse `EvaluateAssemblyRequest` verbatim; new `InstanceEvaluationError`)
      + route `POST /drawing/assembly/evaluate`; `just gen` regenerated.
      Golden `test_drawings_assembly_project`: 2-cube assembly front = 4
      visible + 4 HIDDEN (occlusion), top/right = 8 visible union; rotated
      instance silhouette; single-instance == part (byte-identical); typed
      degradation (bodyless instance / all-bodyless / unsupported view kind);
      determinism. [done 2026-07-23] - [x] SLICE 2 (gateway gate-removal +
      documents resolution): the `assembly_views_unsupported` fast-reject is
      GONE from both compose paths (`_aggregate_compose_request`); documents
      serves
      `GET /assemblies/{id}/evaluation-request` (`build_evaluate_assembly_request` — reuses `ordered_instances`/ `ordered_mates` + the extracted shared `features.evaluation_prefix`);
      the gateway threads the resolved `EvaluateAssemblyRequest` as the new
      additive
      `ComposeDrawingRequest.assembly` (None = part compose, byte-identical).
      Single-level assemblies fully resolve; nested sub-assembly instances →
      empty prefix (typed `no_body`), flatten deferred. Contracts + ts-client
      regenerated. [done 2026-07-24] - [x] (a) **geometry compose branch —
      SHIPPED 2026-07-24** Gates: a compose golden with 2 items + 2 balloons,
      byte-identical no-balloon sheet, `balloon_item_missing` gate. (c) web —
      render assembly views (web reads the SAME `/drawings/{id}/sheet`
      `ComposedSheet`, so (a) alone lights the on-screen sheet up); (d)
      documents — nested sub-assembly FLATTEN (recursive instance walk
      composing placements; today a nested instance degrades to typed
      `no_body`), which also unlocks the recursive/indented BOM. (history:
      docs/BACKLOG-ARCHIVE.md#item-p2-m-drawings-parity-4-assem)

- [ ] (P2, S) Dedicated Hole feature — SLICE 2 TAIL: tapped hole type;
      standard drill-size tables (+ a follow-up MCP/scripting exposure). Seeds
      Drawings hole callouts. [src: AUDIT-PRODUCT.md 2026-07-23] - [x] Tapped
      geometry + DTO (2026-07-25, kernel-architect). v1 threads are
      **COSMETIC** NOT done, with reasons on `ComposedThreadSchedule`: a BOM
      column (a BOM line is a DOCUMENT; a part with four M6 + two M8 has no
      single thread value) and a STEP thread annotation (AP242 PMI, which OCCT
      does not write and AP214 cannot express). - [ ] Standard drill-size
      tables (+ MCP/scripting exposure). The tap drill is already served on
      the drawing's thread schedule; this is the wider stock- drill table +
      agent surface. (history: docs/BACKLOG-ARCHIVE.md#item-cosmetic)

- [ ] (P2, S) Drawings — PROCESS GUARD: a non-default-value compose golden per
      optional authored field. **Nearly closed** — title-block (D1),
      first-angle (D3), and dimension-placement (D2) goldens all landed this
      batch; only the D5 orientation (portrait) golden remains once D5
      authoring ships. [src: AUDIT-ENGINEERING.md cross-cutting]

- [ ] (P2, S) Assembly export — persistent ROTATED multi-instance golden under
      `goldens-assembly/`. Both shipped export goldens
      (`assembly-two-plates-bolted`, `assembly-two-plates-gap`) solve every
      instance to IDENTITY orientation, so the `gp_Quaternion` placement path
      is only guarded by a synthetic test
      (`test_step_assembly_export_nonidentity_ rotation_roundtrip`, added by
      geometry-QA 2026-07-23). Lock a 3-instance / repeated-part /
      non-identity-rotation assembly as a committed golden so the "green
      suite, wrong rotated geometry" hazard is a permanent gate, not a
      synthetic one. [src: GEOMETRY-QA.md 2026-07-23 assembly-export QA]

- [ ] (P1, M) **MB-HOLE — Hole only ever drills the ACTIVE body, while the
      face pick offers every body's faces, so a hole on any earlier body dies
      at Create with `HOLE_OFF_BODY`** ACCEPTANCE: a hole placed on any body's
      face drills THAT body; e2e on the two-body fixture asserting Solved +
      the Δ-volume for a hole on body 1. [src: qa-tester, SEL-7 verification
      2026-08-11] (history: docs/BACKLOG-ARCHIVE.md#item-mb-hole)

- [ ] (P2, M) **PERF-6 — prefetch the prefix an open editor has already
      declared stable** And **prefetch hides latency without reducing work** —
      it cannot bend the N^1.85 curve, and on 4 cores with several users
      uncancellable speculation is a self-inflicted DoS, so it needs a budget
      and real cancellation. Acceptance: a measured drop in perceived
      edit-commit latency at N=100 and N=200 with the CPU budget stated, plus
      a test that a warmed prefix cannot be returned as an answer. [src:
      founder question 2026-07-31 · docs/PERF.md] (history:
      docs/BACKLOG-ARCHIVE.md#item-perf-6)

- [ ] (P3, S) **A sheet too small for its part is still silent.** The N2
      collision check measures view-vs-view, not view-vs-BORDER, so a part
      that outgrows its sheet hangs over the frame with no diagnostic. Wants
      the honest pair: a `views_off_sheet` issue AND an auto-fit scale
      suggestion (the sheet already has a fit-scale control), not just a
      warning. [src: AUDIT-PRODUCT 2026-07-30]

- [ ] (P3, S) **A dimension on a corner ROUND's arc cannot re-anchor.**
      Changing R4 -> R6 moves the arc's centre, so the circular invariant
      (centre + angular station) does not hold and the dimension fails
      honestly rather than re-measuring a differently-placed arc — the
      documented limit of stage-1 naming. The fix is adjacency ("the arc
      tangent to these two faces") = stage-2 provenance (topological-naming
      §2d), not a looser epsilon. [src: topological-naming §11]

- [ ] (P2, S) **GEOM-4 — tier 4's containment check leaves a derivable
      constraint unenforced: when a stored face's area equals the outer
      region's, its centroid MUST equal the outer region's centroid.**
      ACCEPTANCE: the bogus-centroid case above is REFUSED; every existing
      tier-4 golden stays green (their centroids already satisfy the identity,
      since they came from a real subtraction). Small enough to ride with
      GEOM-3 if that lands first, or standalone otherwise. [src: code review
      of 8b95dac, relayed 2026-08-15] TERRITORY:
      `services/geometry/src/geometry/kernel/faces.py` (`enclosing_face_match`).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-geom-4)

- [ ] (P3, XS) **GEOM-5 — an unlisted honest limit for §12a: a hole enlarged
      until it BREACHES the outer boundary (a scallop or edge slot) changes
      the outer wire itself, which is the one invariant tier 4 rests on.**
      Fails SAFE (the outer region shrinks and the upper bound refuses) but is
      the most likely real edit that defeats the claimed invariant, and
      deserves a line in the doc beside the already-documented concave-face
      and grown-face limits. Doc-only; no code change implied. [src: code
      review of 8b95dac, relayed 2026-08-15] TERRITORY:
      `docs/design/topological-naming.md` §12a — land alongside whoever next
      touches GEOM-3/GEOM-4 rather than as a standalone dispatch.

- [ ] (P2, M, recurring) Model-a-REAL-part dogfooding gate — once per phase
      (or ~quarterly), an agent models a complete real product end-to-end
      through the actual app + APIs, verifies against closed-form analytics,
      ships the full package, files every friction point. WB-64 (pass #1,
      2026-07-20) and TB-1 (site toolbox, pass #2, 2026-07-20) both ran; the
      2026-07-23 product-audit pass doubles as a bolted-assembly check (found
      the STEP-export/interference/import gaps now leading Ready). **Pass #3
      ran 2026-08-01 — imported-STEP remix (NEMA 17 vendor plate),
      docs/QA-REVIEW.md: seven closed-form comparisons all exact (vendor
      rev-B/rev-C re-anchoring to 12 s.f.), six defects filed QA3-1..6, two of
      them P1 ergonomics that make the scenario uncompletable in the UI.**
      Next scenario due: spline/loft ergonomic handle (surfacing). [src: WB-64
      retro]

- [ ] (P2, S) SM-fmt-1 — bend-table ONE format, ONE layout pass (frontend +
      geometry). Pre-format display-ready cell strings into
      `ComposedBendTable` server-side (`cells: list[list[str]]` alongside
      numeric `rows`) so `DrawingSheet.tsx` and all three serializers become a
      pure layout pass over shared strings, closing the Python↔TS drift risk
      the current comment-anchored spec only mitigates. Acceptance: DOM
      `BendTable` and SVG/PDF/DXF render identical cell text from the same
      server strings; byte goldens updated + the cross-serializer consistency
      test still passes. [src: docs/UI-REVIEW.md 2026-07-19 P2]

- [ ] (P2, L — spike first, S) Kernel: helical sweep → threads. Any screw
      closure is unbuildable today; OCCT helix wire spike, then size the
      feature slice (pitch, turns, profile, handedness, taper). Sequence after
      the sheet-metal + assembly-interop commitments ahead of it. [src: WB-64
      retro; competitive]

- [ ] (P2, M) Units — sketch-dimension + roll-up unit display (follow-up to
      U2). Sketch driving/driven dimensions (`ConstraintGlyphs`/
      `DimensionForm`) still enter/read canonical mm because their values are
      stored EXPRESSIONS solved server-side (`width/2`, named dims) — unit-
      aware parametric expressions are a distinct design problem. Mass/
      volume/area/extents roll-ups + the box-demo form also stay mm (design
      §"out of v1"). Wire both once the expression-unit model is designed.
      [src: docs/design/units.md §"out of v1"]

- [ ] (P2, M) Viewport makeover Batch 3 remainder / deferred slices — per-face
      pick highlight + tree↔FACE linking (blocked: `OverlayResult` has no
      face→feature attribution — needs a geometry-service slice attributing
      B-rep faces/edges to their source feature; frontend wires once it
      exists); live ghost previews (datum plane cheapest, then
      extrude/pattern; deferred whole to avoid a half-built preview);
      empty-viewport origin triad + resting datum sheets, and parts-home
      thumbnails (needs a last-evaluated-mesh snapshot pipeline). Three
      independent slices bundled here pending split when picked up. [src:
      UI-REVIEW 2026-07-16 remediation items 10–13]

- [ ] (P2, S) Geometry QA: boolean-cut + revolve/sweep-on-offset-plane
      determinism goldens (engineering audit **F4** , remaining slice — cut
      goldens shipped, circular-pattern golden shipped) — no offset-plane
      golden exercises revolve/sweep (code-noted "same path, untested").
      Acceptance: one revolve-or-sweep-on-offset golden, same determinism gate
      as existing goldens. [src: engineering-auditor F4, geometry-qa]

- [ ] (P2, S) Toolbar: sketch-tool overflow flyout — slot/polygon tools
      (splines shipped and are already on the strip). Toolbar system itself
      shipped (`docs/design/toolbar-system.md`); this is its last open
      follow-up. [src: frontend-builder]

- [ ] (P2, M) arq/redis queue runtime — move geometry evaluation from
      sync-inline to the real queue path; geometry gates gain queue-path
      coverage (GEOMETRY-QA gap #2). [src: roadmap, geometry-qa]

- [ ] (P2, S) evaluate_tree: skip tessellation/store for export/measure
      callers (engineering audit **F2** , now also `/overlay` — 3 non-fetching
      callers) — thread a bool through `evaluate_tree` so
      `export_tree`/measure/overlay (which never fetch the GLB) don't churn
      the 64-slot mesh LRU with never-fetched entries, evicting live
      interactive-session meshes. Acceptance: export/measure/overlay requests
      no longer call
      `store_mesh_glb` (test asserts cache occupancy unchanged after N calls);
      evaluate-for-viewport path unaffected. [src: engineering-auditor F2]

- [ ] (P3, S) **QA-CI4-MATE-1 — a mate axis measured ZERO addressable pixels
      under CPU load, and it is the one of three shard-3/4 reds that is NOT
      root-caused.** ACCEPTANCE: the cause is named with a measurement, and
      whichever side is wrong is fixed with a control that fails when the fix
      is reverted. DO NOT "fix" by re-running until green or by dropping the
      40 px floor. [src: qa-tester CI-4 pass, 2026-08-29] (history:
      docs/BACKLOG-ARCHIVE.md#item-qa-ci4-mate-1)

- [ ] (P3, M) **QA-CI4-HEADROOM-2 — shard 3/4 still has ~6 tests at ~2x their
      own timeout, and each needs the same one-at-a-time treatment.**
      ACCEPTANCE: every shard-3/4 test at >=3x its ceiling under 1.5x
      oversubscription, with the census attached; any test that cannot reach
      it says why in its own comment. [src: qa-tester, 2026-08-29] (history:
      docs/BACKLOG-ARCHIVE.md#item-qa-ci4-headroom-2)

## Later (P3)

**Filed groom pass 29 (2026-09-24) — perf/QA residue from the PERF-REAL-2
and E2E-SHARD-COUNT-1 closures:**

- [ ] (P2, M) **PERF-REAL-2B — an edit near the START of a long feature tree
      is still a full cold rebuild; no checkpoint ladder can beat it.**
      ACCEPTANCE: a dependency-aware evaluator (only features that actually
      reference the edited one's outputs re-run) measurably improves an early
      edit (e.g. #3 of 250) below the ladder's own floor — measured today at
      34.0-37.1s either way, i.e. no change, matching a cold rebuild's
      36.1-37.1s. State the new number against both this floor and a cold
      rebuild. Sequenced P2 despite the P3 section (a bigger, riskier slice
      than its neighbours here). [src: `09416c6`/`560eab1` measurement
      (PERF-REAL-2, CLOSED), filed by backlog-groomer pass 29] TERRITORY:
      `services/geometry/src/geometry/kernel/rebuild_cache.py`,
      `services/geometry/src/geometry/kernel/evaluator.py`. agentType:
      kernel-architect. (history: docs/BACKLOG-ARCHIVE.md#item-perf-real-2b)

- [ ] (P3, S) **FRONTIER-OVERSIZE-SIDESLOT-1 — a live oversize checkpoint
      (>128 MiB) is held alone, evicting every other lineage's frontier entry
      on that worker while it is being worked.** ACCEPTANCE: measure whether
      this causes real contention under concurrent multi-user load (today it
      is a single-worker, single-lineage trade the commit accepts
      deliberately — repeats stay hits rather than paying a full rebuild); if
      contention is real, a dedicated side slot for the oversize checkpoint
      (outside the shared 128 MiB budget, still capped at one) is one option
      to evaluate. Revisit only if multi-user large-part contention shows up.
      [src: `83e3c67`, filed by backlog-groomer pass 29] TERRITORY:
      `services/geometry/src/geometry/kernel/rebuild_cache.py`. agentType:
      kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-frontier-oversize-sideslot-1)

- [ ] (P3, XS) **PICK-SPEC-REWEIGH-1 — pick-heavy e2e specs are now ~1.3x
      heavier than the shard-duration manifest's calibration ruler assumes**
      (pick-affordance 382→642s, hole 309→419s, pick-mark-seat 212→336s,
      per `9404cb1`'s 3-frame seat-confirm cost). ACCEPTANCE: re-measure with
      `--emit-durations` in a quiet window (no other load on the box) and
      fold the corrected weights into the manifest so shard balance reflects
      the real cost, not the pre-`9404cb1` one. [src: `d3d0446` shard report,
      filed by backlog-groomer pass 29] TERRITORY:
      `scripts/e2e-shard-plan.py`, its duration manifest. agentType:
      platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-pick-spec-reweigh-1)

- [ ] (P3, XS) **LADDER-PROVENANCE-WEIGH-1 — a checkpoint's weight includes
      the faces the history-lineage provenance memo keeps alive, but that
      share of the total was never isolated.** ACCEPTANCE: measure what
      fraction of a checkpoint's estimated bytes comes from
      `FaceProvenanceRecorder.retained_faces()` alone on a representative
      part (the tray and the 24-lobe NURBS fixture both work), and state
      whether it is worth memo-trimming separately from the shape weight. Not
      a known problem today — a measurement gap, not a defect. [src:
      `8077ede`, filed by backlog-groomer pass 29] TERRITORY:
      `services/geometry/src/geometry/kernel/fork.py`,
      `services/geometry/src/geometry/kernel/provenance.py`. agentType:
      kernel-architect / geometry-qa. (history:
      docs/BACKLOG-ARCHIVE.md#item-ladder-provenance-weigh-1)

**Filed groom pass 27 (2026-09-23) — small, independently-shippable cleanup
found while reconciling `f9fcce6`/`bc53e7d`:**

- [ ] (P3, XS) **DATUM-DEADCODE-1 — `canSubmitOffset` in
      `apps/web/src/features/datum.ts` is used only by its own test.**
      ACCEPTANCE: delete the function and its test cases (or fold the
      equivalent assertion into a `datumSubmitBlocker` test if the coverage is
      otherwise lost); `grep -rn canSubmitOffset apps/web/src` finds nothing
      outside the deletion diff. [src: found while reconciling `17763b5`,
      filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/src/features/datum.ts`, `apps/web/src/features/datum.test.ts`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-datum-deadcode-1)

- [ ] (P3, XS) **SHORTCUT-SHEET-SKETCH-FIT-1 — the shortcut sheet's View group
      still says view keys don't work while sketching, and does not list `0` =
      Fit sketch.** ACCEPTANCE: the View group's note and the Fit row's label
      are correct in BOTH contexts (not sketching: "Fit to the model" / the
      existing note; sketching: "Fit sketch" / a note that says the Fit key
      works while sketching, others do not) — derived from state, not
      hand-kept in sync with `sketchFitShown`. [src: found while reconciling
      `f9fcce6`, filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/src/shortcuts/registry.ts`. agentType: frontend-builder.
      (history: docs/BACKLOG-ARCHIVE.md#item-shortcut-sheet-sketch-fit-1)

- [ ] (P3, XS) **NEXTSTEP-COMMENT-STALE-1 — a stale comment and a
      duplicated-label pair in `apps/web/src/components/nextStep.ts`.**
      ACCEPTANCE: correct the comment to describe the current behaviour;
      either derive `REPEAT_ROWS[].label` from the same source
      `CreateStrip.tsx` reads (if practical) or, if the two must stay separate
      strings, add a unit test that fails when they disagree so the
      duplication is monitored rather than silent. [src: found while
      reconciling `bc53e7d`, filed by backlog-groomer pass 27] TERRITORY:
      `apps/web/src/components/nextStep.ts`, `apps/web/src/components/CreateStrip.tsx`.
      agentType: frontend-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-nextstep-comment-stale-1)

- [ ] (P3, XS) **SCREENSHOT-REFRESH-SKETCH-FIT-1 — founder screenshots for
      sketch-mode specs (`ghost1-*-after.png`) and `next-step-accent-*.png`
      predate `f9fcce6`/earlier sketch-mode changes and are stale.**
      ACCEPTANCE: run `UPDATE_SCREENSHOTS=1 pnpm --filter @loft/web e2e` for
      the affected specs, review the diffs (this is the one check that asks
      "is the thing legible", per CLAUDE.md), and surface the refreshed
      before/after pair to the founder at the next milestone rather than
      silently committing new PNGs. [src: found while reconciling `f9fcce6`/
      `bc53e7d`, filed by backlog-groomer pass 27] TERRITORY:
      `docs/screenshots/`. agentType: frontend-builder or qa-tester. (history:
      docs/BACKLOG-ARCHIVE.md#item-screenshot-refresh-sketch-fit-1)

**Filed groom pass 25 (2026-09-15):**

- [ ] (P3, S) **AREA-INTEGRATION-1 — surface area has the same fixed-order
      integration bias volume had (F1), and it is deliberately NOT fixed.**
      ACCEPTANCE (when someone picks this up): either a smarter integration
      scheme that DOES converge on real NURBS surfaces at acceptable cost, or
      a documented decision to leave area on the fixed order permanently with
      the bias bounded and stated. Do not "fix" this by copying volume's
      `eps=1e-10` verbatim — it was measured NOT to help here. [src:
      geometry-qa gauntlet + F1 fix, `docs/GEOMETRY-QA.md`/`f7cd483`,
      2026-09-15] TERRITORY:
      `services/geometry/src/geometry/kernel/measure.py`. agentType:
      kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-area-integration-1)

- [ ] (P3, XS) **GEN-CHECK-VERDICT-1 — `gen-check`'s green message doesn't
      mention its third leg.** ACCEPTANCE: the verdict line names all three
      legs. [src: code review P2-8, `docs/CODE-REVIEW.md`, `451245c`]
      TERRITORY: `scripts/gen-check.sh`. agentType: platform-builder.
      (history: docs/BACKLOG-ARCHIVE.md#item-gen-check-verdict-1)

- [ ] (P3, M) **DOCS-EXPLORER-1 — decide whether to restore an interactive API
      explorer, and how.** ACCEPTANCE: a decision recorded here or in
      `docs/OPERATIONS.md`, with whichever option implemented. [src: code
      review clean-bill note, `docs/CODE-REVIEW.md`, `451245c`; `725bc4b`]
      TERRITORY: `docs/QUICKSTART.md`, `packages/py-kit` (if (b) or (c)).
      agentType: platform-builder / founder decision. (history:
      docs/BACKLOG-ARCHIVE.md#item-docs-explorer-1)

- [ ] (P3, S) **SHARD-MANIFEST-CI-1 — the e2e duration manifest
      (`scripts/e2e-durations.json`) was measured on this local container, and
      CI's relative per-file costs differ enough to move the answer.**
      ACCEPTANCE: the manifest's provenance note states which run it was
      derived from; a re-measurement on CI shows the shard spread converging
      closer to 1.00x than the current 1.16x, or the ticket records why it
      does not. [src: orchestrator CI-runner verification, filed by
      backlog-groomer pass 19] TERRITORY:
      `scripts/e2e-shard-plan.py`, `scripts/e2e-durations.json`, `.github/workflows/e2e.yml`.
      agentType: platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-shard-manifest-ci-1)

- [ ] (P3, S) **QA-CI4-LINES-1 — a shard verdict's `file:line` is not a stable
      identifier: 45 of 169 specs report a different line between runs of
      byte-identical source.** ACCEPTANCE: the verdict names a test the reader
      can find, demonstrated on a run that reproduces the drift. [src:
      qa-tester CI-4 pass, 2026-08-29] (history:
      docs/BACKLOG-ARCHIVE.md#item-qa-ci4-lines-1)

- [ ] (P3, XS) **INVARIANTS-PROJECTION-1 — the camera-projection helper
      `projection.spec.ts` uses privately now has a second real use, this
      repo's own stated threshold for extraction.** ACCEPTANCE: one
      definition, two call sites, no behaviour change (both existing specs
      stay green); a third future consumer needs no duplication to reuse it.
      [src: SEL-6 qa-tester agent report on `153681b`, filed by
      backlog-groomer pass 18] TERRITORY:
      `apps/web/e2e/invariants.ts`, `apps/web/e2e/projection.spec.ts`, `apps/web/e2e/pick-affordance.spec.ts` (or wherever `qa-sel6-verify` lives).
      agentType: frontend-builder or qa-tester. (history:
      docs/BACKLOG-ARCHIVE.md#item-invariants-projection-1)

- [ ] (P3, XS) **PGTEST-GATE-VACUOUS-NONGOAL — record, don't fix, the one case
      PGTEST-GATE's verdict deliberately leaves unfloored: PostgreSQL present
      but zero pg-requiring tests selected.** ACCEPTANCE: none — this ticket
      closes by staying a documented decision, unless a future audit finds the
      vacuous case actually masking a real regression, in which case re-open
      with that evidence. [src: PGTEST-GATE platform-builder report,
      2026-08-28, recorded by backlog-groomer pass 18] TERRITORY: none
      (process note). agentType: n/a. (history:
      docs/BACKLOG-ARCHIVE.md#item-pgtest-gate-vacuous-nongoal)

- [ ] (P3, S) **AUDIT-HOUSEKEEPING — bundle of small engineering-audit
      carry-overs (`docs/AUDIT-ENGINEERING.md` "Pass 7" M6(b)+M10), one slice,
      none urgent alone.** [src: docs/AUDIT-ENGINEERING.md "Pass 7" M6(b)+M10,
      filed by backlog-groomer pass 8] TERRITORY:
      `.claude/workflows/*.js` (Integrate phase), `docs/ROADMAP.md` +
      `docs/BACKLOG.md` (citation sweep), `apps/web/e2e/ viewport-makeover.spec.ts`, `scripts/check-compose.py`,
      gateway alembic config,
      `services/gateway/tests/ test_assembly_import_chain.py`. agentType:
      platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-audit-housekeeping)

- [ ] (P3, XS) **QA-REVIEW-OWNER — `docs/QA-REVIEW.md` is cited by ROADMAP and
      BACKLOG but owned by no agent, and `qa-tester.md` instructs "run the
      Playwright suite in both projects" when `playwright.config.ts` declares
      none.** ACCEPTANCE: `docs/QA-REVIEW.md` either has a real writer or is
      deleted with its citations removed; `qa-tester.md` no longer asks for a
      step the config can't do. [src: docs/AUDIT-ENGINEERING.md "Pass 7" M9,
      filed by backlog-groomer pass 8] TERRITORY:
      `.claude/agents/qa-tester.md`, `docs/QA-REVIEW.md`, `docs/ROADMAP.md`/`docs/BACKLOG.md`
      citations. agentType: platform-builder. (history:
      docs/BACKLOG-ARCHIVE.md#item-qa-review-owner)

- [ ] (P3, XS) **GQA-2 — a selector "authored before the GEOM-3 change" and
      "OCCT couldn't build the outer-wire region at pick time" produce the
      IDENTICAL stored signature, so a future document-side re-emit cannot
      tell them apart.** ACCEPTANCE: a new test forces an OCCT region-build
      failure at pick time and asserts the resulting signature is
      distinguishable (by field, not just by None-ness) from one from a
      genuinely pre-GEOM-3 selector. [src: geometry-qa independent
      verification of GEOM-3, `0628ceb`, 2026-08-16, docs/GEOMETRY-QA.md
      "GQA-2"] TERRITORY:
      `services/geometry/src/geometry/kernel/faces.py` (`_signature_dto`), `packages/py-kit` (schema, if a field is added).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-gqa-2)

- [ ] (P3, XS) **GQA-3 — GEOM-3's tier 4a cost moved from the resolve path (a
      500x win, 1.70 us vs 4b's 866 us per candidate) onto the interactive
      viewport OVERLAY route, which is unconditional and wasn't in the
      builder's cost table.** ACCEPTANCE: the three named goldens' warm
      overlay cost returns to within 10% of pre-GEOM-3 baseline;
      `test_benchmarks.py` gains a tripwire for the overlay route specifically
      (the gap this pass found — cold-rebuild and isolated `planar_faces`
      benchmarks already exist but neither covers this route). [src:
      geometry-qa independent verification of GEOM-3, `0628ceb`, 2026-08-16,
      docs/GEOMETRY-QA.md "GQA-3"] TERRITORY:
      `services/geometry/src/geometry/kernel/faces.py` (outer-boundary invariant construction), `services/geometry/tests/ test_benchmarks.py` (new overlay tripwire).
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-gqa-3)

- [ ] (P2, XS) **GQA-4 — the golden corpus exercises `settle()`'s FAST path
      only; every defect SETTLE-2/SETTLE-3 found lived in the ladder the
      goldens never reach.** Also folds in N8(c) (`docs/AUDIT-ENGINEERING.md`
      "Pass 9"): one AST-swept test, `test_drawings_measure.py:898-910`,
      asserts only inside a loop over an unguarded filter
      (`for arc_like in (e for e in top.edges if …)`) — add a floor
      (`assert len(...) >= 1`) so an empty filter can't pass silently,
      mirroring `test_faces_geom3_qa.py:253`'s existing pattern. [src:
      docs/AUDIT-ENGINEERING.md "Pass 9" N7/N8(c), filed by backlog-groomer
      pass 11] TERRITORY:
      `services/geometry/goldens/**` (new fixture), `services/geometry/tests/test_drawings_measure.py`.
      agentType: kernel-architect. (history:
      docs/BACKLOG-ARCHIVE.md#item-gqa-4)

- [ ] (P3, XS) **REV-3 — FB-7's collapsed rail tab aligns to the wrong edge on
      the RIGHT rail** Reachable in the shipped flow: `HoleEditor` is
      unconditionally `seat="right"` and the inspector is mounted during hole
      editing. FIX:
      `railed ? cx("shrink-0", side === "right" ? "self-end" : "self-start")`.
      Cosmetic — the tab stays visible and clickable — but one line, and it
      sits in the flow FB-7 exists to fix. Also note (a) of the same lens:
      collapsing the inspector leaves ~91 px of measured dead column; worth a
      note, not a restructure. [src: ultracode review, 2026-08-13] (history:
      docs/BACKLOG-ARCHIVE.md#item-rev-3)

- [ ] (P3, S) **REV-4 — six more untrue statements in comments and docs, plus
      two dead code paths** The step-timeout change is right for its other
      stated reason, so nothing needs reverting — soften the sentence or check
      it against one real timed-out job. (g) `ChromeRail.test.tsx:54` — the
      second case's assertion is byte-identical to the first's and its title
      claims a `data-viewport-chrome` check it does not make. It can fail, so
      it is not dead; it adds zero coverage. [src: ultracode review,
      2026-08-13] (history: docs/BACKLOG-ARCHIVE.md#item-rev-4)

- [ ] (P3, XS) **SPEC-3 — the live-extrude-ghost gate is a thin statistical
      margin, and it fails on framing rather than on the ghost** The spec's
      comment calls a bare sketch "relatively few shades" while the measured
      baseline was 328, so the premise no longer describes the scene it runs
      in. FIX: assert on something the ghost alone controls (its own pixels
      inside a known rect, or a token-coloured sample), or restate the floor
      around a margin measured across runs instead of a hardcoded +8. Same
      class as the CI-1 fix — pin the claim to hundreds-vs-zero, not to a
      framing-specific ratio. [src: orchestrator CI root-cause, 2026-08-11]
      (history: docs/BACKLOG-ARCHIVE.md#item-spec-3)

- [ ] (P3, XS) **SEL-6-AFTERCARE (renamed groom pass 15 from a collided
      "SEL-8" id — the fillet edge-pick hover-highlight ticket also used
      SEL-8, filed later and unrelated; this is the older ticket) — five loose
      ends the review logged green** Fails toward a false RED, so robustness
      only. (e) `partView.ts:163` — only `hidden` feeds `pickHiddenFaces`, so
      a GHOSTED body still both eats and offers picks. Defensible and
      pre-existing (Fusion keeps translucent bodies selectable), but now that
      the hidden case is spelled out at length the omission reads as an
      oversight; one explicit line in the module doc. [src: code-reviewer,
      SEL-6 slice 2026-08-08] (history:
      docs/BACKLOG-ARCHIVE.md#item-sel-6-aftercare)

- [ ] (P2, S) **SEL-5 — no gate proves the addressed face's trace respects
      OCCLUSION** The 2026-08-06 fix (depth-tested `Line2` + faint x-ray pass)
      is evidenced by founder screenshots
      (`docs/screenshots/sel1-bore-trace-*`) and nothing else, because every
      instrument we own for this is a pixel census and the honest direction
      here is FEWER lit pixels — exactly the "a census can reward the broken
      screen" trap FB-17d records. Wanted: an assertion tied to WHERE the
      brass lands (inside the hole's silhouette vs across the plate) rather
      than to how much of it there is. The bored-plate fixture and the
      island-finding sweep that addresses its bore wall already exist in
      `e2e/face-hover.spec.ts`. [src: code review 2026-08-06] (history:
      docs/BACKLOG-ARCHIVE.md#item-sel-5)

- [ ] (P2, S) **A bound sketch undone to ZERO entities cannot persist that
      state** (`apps/web`). `PartPage.persistBuffer` early-returns when
      `entities.length === 0`, which predates sketch undo (nothing could
      shrink the buffer before FB-23), so undoing the last entity of a SAVED
      sketch shows an empty sheet while the server keeps the last geometry —
      and Finish then closes without reconciling them. Fix in the sync loop,
      not the store: an empty bound sketch is a legal state to save. [src:
      FB-23 as-built]

- [ ] (P3, XS) **Fold the two private `calibratePlane` copies into
      `e2e/planeMap.ts`** (`apps/web`). `constraints.spec.ts` and
      `sketch-snap.spec.ts` each carry their own copy of the plane→screen
      calibration; the shared module landed with FB-22 rather than adding a
      third. Next time either spec is opened, import it. [src: FB-22 as-built]

**QA verdicts on the founder block (qa-tester, 2026-08-01, HEAD + bisect):**
`d8a4126` (PERF-4b) is **EXONERATED — do not revert**: face picking uses drei
`Html` DOM buttons, `ModelMesh` has no click handler at any of `3cf6650` /
`d8a4126` / `3f4fbe6`, and every pick probe is identical to the character at
all three. **FB-2 does not reproduce as stated** (a clean click selects the
line and `D` dimensions it, everywhere) — FB-12/FB-13 are the real defects
behind it.

**FB-3/FB-5 reproduce** diagnosis is REFUTED** — the ink renders fine; the
plane card fills the frame as a featureless grey slab with no grid, no body,
no scale, and `countSketchInkPixels` goes UP 500× when the sketch becomes
unusable, so a gate built on it would pass. **FB-9 is not wrong geometry**:
solid min along the normal equals the plane offset to 0 on XY, XZ, YZ and
XY+30, volume exactly 10000.000000 mm³, footprint exactly the profile — so it
is the pre-`5bd4c46` camera snap or a stale Codespace bundle (see FB-11).
(history: docs/BACKLOG-ARCHIVE.md#meta-later-fb-3-fb-5-reproduce-32-of-145)

- [ ] (P2, S) **SEL-3 — stacked-candidate count badge** (`apps/web`). When
      `pickCandidates(...).length > 1` (sketch) or a raycast hit disagrees
      with a nearby armed-pick `PickNode` within tolerance, show a small `+N`
      badge beside the SEL-2 marker (reuses the app's one round-badge
      convention — no new tokens) so cycling is discoverable, not silent.
      Design + acceptance A4: `docs/design/pre-selection.md` §3, §6. [src:
      founder]

- [ ] (P2, S) **SEL-5 — the PickNode "DOM-square blanket" is a measured,
      still-open defect** `docs/UI-REVIEW.md`'s 2026-07-24 P2 is unfixed:
      every armed-pick target paints a visible reticle AT REST, always (~22
      squares/diamonds on a six-face plate the moment Measure arms). Reduce
      `PickNode`'s rest-state opacity so the topology highlight (not the DOM
      grid) carries the "what's under the cursor" read; hover/focus/selected
      states unchanged. Cheap, isolated, independent of SEL-1's larger raycast
      plumbing — can ship first. Acceptance A7: `docs/design/pre-selection.md`
      §6. [src: founder] (history: docs/BACKLOG-ARCHIVE.md#item-sel-5-2)

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
      a keyboard user cannot Tab to an existing sketch entity or point. Real
      fix mirrors the lift `FacePickOverlay`/`EdgePickOverlay` already paid:
      give sketch entities/points focusable `PickNode`-style targets. Named
      honestly as an open a11y gap, not implied-closed by SEL-2/SEL-3 (those
      extend the *visual* marker; this is the missing input path).
      `docs/design/pre-selection.md` §5, §7. [src: founder]

- [ ] (P3, L) **CONC-5 — OCP does not release the GIL, so one geometry worker
      can never use more than one core** Measured at **1.05-1.15 cores** with
      1/2/4/8 concurrent requests in flight and 11-18 OS threads live;
      throughput is flat and latency linear in user count. Every other item
      above is a workaround for this. A `py::gil_scoped_release` around the
      long OCCT calls in OCP would make one worker use one machine; short of
      that, the per-core-worker rule in `docs/OPERATIONS.md` §6 stands. Filed
      at P3 because it is upstream work with a shipped workaround, not because
      it is small. [docs/PERF.md 2026-08-01] (history:
      docs/BACKLOG-ARCHIVE.md#item-conc-5)

- [ ] (P3, S) **CONC-7 — nobody sized the connection pools, and the defaults
      are wrong in the direction that hurts** Neither pool is configured:
      `py_kit.db` takes SQLAlchemy's default 5+10 connections per service
      process, and `create_upstream_client` takes httpx's default 100 max
      connections to geometry — i.e. the gateway will pile 100 requests onto a
      worker with one effective core. Nothing exhausted during the 2026-08-01
      run, so this is not a live defect; it is an undocumented default that
      makes CONC-2 worse and belongs in `docs/OPERATIONS.md` §6 with a number
      behind it. [docs/PERF.md 2026-08-01] (history:
      docs/BACKLOG-ARCHIVE.md#item-conc-7)

- [ ] (P3, S) **#WS3 — drag a register row onto a divider to file it.** Drag
      is now purely additive — HTML5 dnd on `DocumentRegisterRow` with
      `RegisterFolderRow` as the drop target, calling the same
      `onMoveDocument`. Also open: moving a FOLDER (the endpoint and its cycle
      rejection exist and are tested; no UI calls `moveFolder` yet), and
      deep-linking the current folder into the URL so a folder view can be
      shared or reloaded in place. [src: #WS2 follow-up] (history:
      docs/BACKLOG-ARCHIVE.md#item-p3-s-ws3-drag-a-register-r)

- [ ] (P2, M) **Web authoring for the mirror scope** Surface the four typed
      refusals by
      `upstream_feature_id` (the offending SELECTED feature, so the tree row is highlighted, not the mirror).
      Defaulting the UI to `features` while the schema defaults to `body` is
      legitimate and probably right (design §11.2). Open UX question §11.4:
      warn when a selected feature is suppressed — today that is a typed
      `references_suppressed` error, so the warning is a pre-flight nicety,
      not a correctness gap. [src: mirror-semantics §11.2/§11.4] (history:
      docs/BACKLOG-ARCHIVE.md#item-p2-m-web-authoring-for-the-mi)

- [ ] (P3, S) **The v1 cut slot still records only extrude-cut + hole.**
      Consequence: a `body`-scope mirror after a revolve/sweep/loft CUT still
      takes the reflect-and-union path and can fill that void — the FINDINGS
      #2 class, for the three non-extrude cuts. Fixing it is a real behaviour
      change needing its own goldens; the `features` scope already gives users
      a correct answer today. [src: mirror v2 implementation 2026-07-30]
      (history: docs/BACKLOG-ARCHIVE.md#item-p3-s-the-v1-cut-slot-still-re)

- [ ] (P3, M) **Real sheet numbers: a stored per-owner monotonic sequence.**
      The honest fix above keeps the gutter truthful but a drawing register
      arguably wants a durable sheet number a person can cite across deletes —
      that is a `documents` column + backfill (assign on insert, never reuse),
      plus a decision on whether it is per-owner or per-project. Only worth
      building if the founder wants citable sheet numbers; the ordinal is not
      a placeholder for it, it is a different, correct thing. [src: UI-REVIEW
      2026-07-30 P2]

- [ ] (P3, S) **Same last-evaluate record for assemblies + drawings.** Parts
      got `0012`; the assembly and drawing registers still cannot say "is
      broken". Assemblies have their own evaluation-request path, so the
      pattern ports directly (`doc_version` in place of `tree_version`); a
      drawing's health is really its source documents' plus compose, so decide
      what it claims before building it. [src: feature-tree.md §4.4a stated
      limit]

- [ ] (P3, S) **`draft` propagates along a tangent chain with no UI/doc
      warning.** After an r4 corner fillet makes all four walls
      tangent-continuous, drafting the ONE picked +X face tapers all four
      walls plus the four fillet cylinders (1361.7627 mm³ removed vs 314.9581
      for the named face). OCCT-correct (`BRepOffsetAPI_DraftAngle` propagates
      through tangent continuity) and usually desirable, but a picked-face UI
      never says so — doc + editor copy. Pinned by
      `test_observed_limit_draft_propagates_along_a_tangent_chain`. [src:
      GEOMETRY-QA 2026-07-25 composition matrix]

- [ ] (P3, XS) **QA3-4 — the PUBLISHED overlay contract still promises the
      pre-PERF-4b glTF layout.** Since `d8a4126` that holds only on the
      UNFUSED encoding; below 12 triangles/face the ordinal must be recovered
      from `extras.LOFT_face_triangles`. Measured: 11 B-rep faces arriving in
      6 primitives. `apps/web` does it right — the CONTRACT is what is wrong,
      and a third-party client written to it mis-highlights every sparse part.
      Fix the description + regenerate. [docs/QA-REVIEW.md 2026-08-01 QA3-4]
      (history: docs/BACKLOG-ARCHIVE.md#item-qa3-4)

- [ ] (P3, M) **QA3-5 — small features are tessellated ~200x finer than the
      requested deflection, because the angular criterion is
      radius-independent** A 24-face plate meshes to 4 846 triangles, ~1 500
      of them in six cylinders under 6 cm² total, and the density pushes such
      parts to 202 tris/face — well past PERF-4b's threshold of 12, so they
      decline the fusion that would have removed their per-face JSON. A vendor
      STEP with a hundred tapped holes pays it on every hole. Acceptance:
      honour the linear deflection as the binding criterion on small radii (or
      scale the angular one by radius); goldens re-baselined in the same
      commit since `mesh_glb_id` is a content hash. [docs/QA-REVIEW.md
      2026-08-01 QA3-5] (history: docs/BACKLOG-ARCHIVE.md#item-qa3-5)

- [ ] (P3, XS) **QA3-6 — `data-camera-pos` reads like a live camera hook and
      is not.** It is stamped only on a programmatic view SETTLE (fit / view
      command), never on a user orbit or pan, so a touch-orbit probe that
      WORKS looks broken — it produced a false positive during dogfooding pass
      #3 before being root-caused. Either stamp it on control change or rename
      it to say what it means. (`import-remix.spec.ts` asserts on a canvas
      raster fingerprint instead.) [docs/QA-REVIEW.md 2026-08-01 QA3-6]

- [ ] (P3, S) **A lost dimension's caption can overrun into a neighbouring
      view — and it does so identically on the exported sheet** The fix
      belongs in the COMPOSER, not the client: the SVG export has
      byte-identical placement, so a client-side nudge would make screen and
      print disagree — which is the defect class this repo keeps closing.
      Acceptance: the caption is placed against the view's measured extents
      (the N2 collision machinery already exists), with a compose golden that
      has a caption long enough to have overrun. [src: handback from the #58
      settings slice, 2026-07-31] (history:
      docs/BACKLOG-ARCHIVE.md#item-p3-s-a-lost-dimension-s-capti)

- [ ] (P3, M) Settings rows that need a PROPERTY before they can be rendered
      (frontend-builder, 2026-07-31 — deliberately omitted from the shipped
      `/settings` sheet rather than faked). Each needs its backing first:
      **angular unit** (`packages/design/src/units.ts` is length-only — no
      angular vocabulary, and angles are authored in degrees everywhere),
      **display precision** (`formatLength` takes `maxFractionDigits` but
      nothing carries a user value down to the readouts), **grid/snap step**
      (a sketch-store constant being made configurable in a concurrent slice —
      read THAT value, never define a second one), and **document-scope
      settings generally**: the sheet is application-scope only because a
      document setting needs an open document, so the unit/material controls
      stay in the workspace until there is a document-settings surface there.
      [src: founder #58, scoped]

- [ ] (P3, S) Drawings compose: the failed-view dashed box overlaps its error
      text with the view caption (e.g. "FLAT PATTERN") — small `_emit_view`
      polish; changes byte-pinned compose goldens, so it rides its own slice.
      Split from the shipped hem-on-flange flat-pattern fix (2026-07-22).
      [src: founder dogfooding — TB-1]

- [ ] (P3, S) STEP import parse-worker — cap parse WORKING-SET memory + config
      hardening (code-review 🟢 on `f5a9038`): the STEP subprocess now bounds
      CPU time (`RLIMIT_CPU`) but NOT resident memory — Add
      `RLIMIT_AS`/`RLIMIT_DATA` alongside the CPU limit in
      `_step_parse_worker._apply_cpu_limit` (sized not to reject a legit large part),
      and (a) map an OOM-`SIGKILL` to a memory/parse-failure code rather than
      `import_parse_timeout`, (b) clamp/validate a non-finite
      `STEP_IMPORT_TIMEOUT_SECONDS` in
      `GeometrySettings` (an inf/nan budget currently degrades every import to `parse_failed` via an uncaught `math.ceil`).
      Pre-existing, non-attacker-reachable footguns + a real memory-DoS gap.
      [src: code-reviewer] (history:
      docs/BACKLOG-ARCHIVE.md#item-p3-s-step-import-parse-worker)

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
      trio and Drawings' own assembly-view work (Ready). [src:
      AUDIT-PRODUCT.md 2026-07-23]

- [ ] (P3, S) Part-version pinning for assemblies — instances track a part's
      live tip today; immutable part versions give deterministic, frozen
      assemblies. [src: AUDIT-PRODUCT.md 2026-07-23]

- [ ] (P3, S) Spline profile builder: named tolerance + non-consecutive-
      coincidence guard (engineering audit **F5** ) — promote the inline
      `abs_tol=1e-9` (kernel/extrude.py:186) to the module's existing
      `PROFILE_WIRE_TOLERANCE`; extend the coincident-fit-point guard beyond
      consecutive pairs. [src: engineering-auditor F5]

- [ ] (P3, M) Thread feature — cosmetic/modeled threads on a hole/cylinder,
      driven by a thread-standard library. [src: competitive]

- [ ] (P3, S) UI: warn before a fillet radius risks a thin-shell rim collision
      (showcase F3) — backend behavior is correct (OCCT refuses the
      collision), this is discoverability only. [src: product-auditor
      showcase-QA F3] >>> ATTRIBUTION NOTE (orchestrator, 2026-07-30): the
      three P3 items below were >>> filed by kernel-architect as SH-1
      follow-ups, but landed in commit `33b1b5a` >>> — an orchestrator commit
      about an unrelated gate — because I ran >>> `git add docs/BACKLOG.md`
      while their uncommitted hunks were in the file. >>> The protocol is
      stage YOUR hunks, never a shared doc wholesale. No work was >>> lost;
      the authorship in git history is simply wrong, and `33b1b5a`'s message
      >>> does not mention these items.

- [ ] (P3, S) A typed `warnings` channel on `FeatureResult` + a distinct
      `shell_pinched_wall` code — the honest follow-up to SH-1 (GEOMETRY-QA
      2026-07-30). A thickness of exactly half an internal wall is refused
      today under `shell_thickness_too_large` because the wire has no way to
      say "built, but read this"; the kernel already computes the slit's area
      and position, so the only missing piece is the schema. py-kit +
      generated clients + tree-panel copy — NOT a kernel change. [src:
      kernel-architect, SH-1]

- [ ] (P3, S) Kernel: bucket `find_zero_width_slits` by support plane if a
      shell of a many-FACE body ever becomes a real workflow. The pair test is
      O(N^2) float arithmetic — measured ~1.2 us/pair (0.56 ms on the 11-face
      golden tray, 6.3 ms on a 102-face comb), so a few hundred faces is still
      cheap next to `MakeThickSolid`, but an imported STEP part with thousands
      would not be. Bucketing must not quantise the comparison bounds (a
      missed bucket = a missed slit). [src: kernel-architect, SH-1]

- [ ] (P3, S) Sheet metal: floor `SheetMetalHemParamsV1.bend_radius_mm` at the
      kernel linear tolerance (1e-4 mm). A closed hem's air gap is
      `2 x radius` and the schema only requires `> 0`, so radius 1e-6 ships a
      body whose two layers are 2e-6 mm apart — a zero-width slit by the
      kernel's own tolerance (300 mm² measured), reported `ok`. Pinned live by
      `test_observed_limit_a_sub_tolerance_closed_hem_ships_a_slit`; not
      reachable by a sane author in mm units, and the fix belongs in the
      py-kit schema (a validation 422), not a per-verb kernel probe. [src:
      kernel-architect, SH-1 sibling audit]

- [ ] (P3, M) Shell: partial-shell / add-a-flange-after-shell workflow — needs
      a design note first (what "a selected region" means for
      `MakeThickSolid`). Not urgent: showcase routed around it. [src:
      qa-tester showcase-QA]

- [ ] (P3, M) STEP import v2: blob-backed storage for large files — the
      additive `kind:"blob"` migration path is already seeded; a real
      engineering/scaling concern once imported-part assemblies bloat the tree
      (re-confirmed 2026-07-23). [src: roadmap, step-import.md;
      AUDIT-PRODUCT.md 2026-07-23]

- [ ] (P3, L) STEP import v2: IGES, assembly product-structure, sew/repair
      healing — (1) IGES as a second import format; (2) named ASSEMBLY
      product-structure (STEP AP242 hierarchy → an assembly of instances,
      distinct from MB-4b's flatten-to-lumps); (3) a real sew/repair healing
      report. Split into independent slices when picked up. [src: roadmap,
      geometry-qa, step-import.md]

- [ ] (P3, S) Sheet-metal bend-tree unfold — optional hardening (code-review 🟢
      on `66aee0a`): (a) add a RUNTIME invariant inside `_unfold_bend_tree`
      asserting the assembled union-loop shoelace area ≈ summed
      `flat_area_mm2` (raise `UnfoldOverlapError` otherwise) so "the outline
      tiles the blank" is load-bearing at runtime, not only in the golden
      tests — closes the one theoretical path (flange vs non-adjacent BA-strip
      overlap merging into a clean loop) the flange-rect-only overlap gate
      doesn't cover; (b) note the `_face_key` normal-6dp/centroid-4dp
      tree-node rounding (fine for mm-scale parts, in-run-only key). Neither
      demonstrated on a real body. [src: code-reviewer]

- [ ] (P3, S) Sheet-metal corner relief — optional hardening (code-review 🟡/🟢
      on `d1aaadd`): (a) an oversized relief (`size_mm`/`relief_ratio`
      developing a notch deeper than ~half the shared flange width) produces a
      VALID body but fails only at draw time on the relieved flat-pattern
      unfold — move the check EARLIER, into the corner-relief evaluator, so it
      degrades to a typed `corner_relief_failed` at feature-eval time
      (matching the honest-degradation contract) instead of surfacing
      downstream in the flat-pattern view; (b) 🟢 `cut_relief_tools`'s
      `(body, tools)` split is currently exercised only through
      `apply_corner_relief`'s single-relief path — YAGNI signature, fold back
      inline if no second caller materializes; (c) 🟢 note the relief-notch
      `content_hash` is order-sensitive on the tool subtraction sequence
      (deterministic today via the feature-tree order, but not intrinsically
      order-free). None blocks a real user model; all are out-of-scope-input /
      internal-shape notes. [src: code-reviewer, corner-relief multi-corner
      review]

- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents `HTTPValidationError`) [src:
      kernel-architect]

- [ ] (P3, S) CI: pin GitHub Actions to full commit SHAs — cheap supply-chain
      hardening. [src: code-reviewer]

- [ ] (P3, S) geometry worker: move import-time settings read to lazy/DI —
      cosmetic. [src: code-reviewer]

- [ ] (P3/P4, L) Parametric ⇄ direct-modeling mode toggle — Plasticity's core
      wedge, not urgent: doesn't flip a current ❌ row since Loft's parametric
      core isn't finished yet. [src: competitive]

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
      edges only reveal their pickability on hover/focus; add a quiet resting
      cue for a first-run user. [src: docs/UI-REVIEW.md 2026-07-17]

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
      never fetches. DRY-sanctioned for now; add a body-only eval entry point
      when drawing-eval volume makes it matter. [src: code-review of
      `d65caff`]

- [ ] (P3, S) History-tree drag-reorder — distinct from the rollback bar
      (which moves the build point, not an action stack) and from Feature
      suppress (promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src:
      product-auditor Pass 2]

- [ ] (P3, M) 2-direction linear pattern — pattern breadth gap (mirror-feature
      promoted to Ready P2, AUDIT-PRODUCT.md 2026-07-23). [src:
      product-auditor Pass 2]

- [ ] (P3, S) A friendlier `boolean_failed` error message (today's is the
      generic OCCT-raise catch-all). [src: product-auditor Pass 2]

- [ ] **SPECULATIVE — not sized, not sequenced, candidate future vertical
      only.** AEC/BIM domain layer (Revit-class: walls-that-host-openings,
      levels/grids as spine, IFC interop, schedules) — see
      `docs/design/aec-bim.md` for the full pre-greenlight scoping. Honest
      verdict there: a legitimate 2027+ platform bet comparable in size to
      everything Loft has shipped through Phase 4, gated on a domain
      correctness bar (code/egress/energy) the team doesn't have — NOT a
      near-term pillar, does not compete with Phase 4b/5 for attention. [src:
      founder]

- [ ] (P3, XS) **SPEC-2 — `qa-sel4-verify.spec.ts`'s hidden-body leg sits on
      its own timeout ceiling** Found 2026-08-11 by qa-tester: the test
      declares `test.setTimeout(180_000)` and measured 2.5 m and 2.9 m in
      isolation and 3.0 m in a five-spec run, where it FAILED on the ceiling —
      i.e. ~17 % headroom on a gate whose cost grows with the canvas sweep.
      Not a product defect (it passes alone, twice), but a red CI shard
      waiting for a slower runner. FIX: raise the budget or thin the sweep;
      same class as the contention-robustness hardening already applied to the
      founder-flow specs. [src: qa-tester, SEL-7 verification 2026-08-11]
      (history: docs/BACKLOG-ARCHIVE.md#item-spec-2)

- [ ] (P3, XS) **A11Y-SKETCHSTRIP-DUP-1 — three `SketchStrip` buttons now say
      the same thing twice, once in the name and once in the description.**
      ACCEPTANCE: no `ToolButton` in `SketchStrip.tsx` has an `aria-label`
      that repeats its own caption, and the FB-13 e2e cases still assert the
      consequence is announced somewhere. [src: frontend-builder,
      A11Y-TOOLBTN-1 measurement 2026-08-28] (history:
      docs/BACKLOG-ARCHIVE.md#item-a11y-sketchstrip-dup-1)

## Blocked (environment/timing — not build-blocked)

- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop runs unattended. [src:
      retro]

- [ ] (P2, XS) **Fill in `e2e.yml:88` and `ci.yml:83`'s CI numbers** Still
      owed: read the latest green `e2e complete` job log for `--timeline` and
      the `python` job's Pytest step duration, and write both numbers into the
      two files' comments — the 30-min ceiling's own justification comment is
      still stale even though the number it argues for currently holds. [src:
      AUDIT-ENGINEERING.md Pass 7 M5+M10; CI reading groom pass 26] (history:
      docs/BACKLOG-ARCHIVE.md#item-p2-xs-fill-in-e2e-yml-88-an)

- [ ] (P2, S) **RETRO §1.1's durable server-side Routine** — needs one founder
      approval, denied four times; the loop lost 58.3 hours between `5bfb528`
      and
      `22a44bb` (container reclaimed, restarted by hand, an 8th recurrence)
      while the batch's own work rate was excellent (56% feat/fix). This is
      now the dominant term in throughput, not the work rate itself — "the
      single highest-value unblock available" (`docs/RETRO.md` §1.1), and the
      only item in either audit this batch the engineering org cannot fix for
      itself. [src: AUDIT-ENGINEERING.md Pass 7 M6(a); docs/RETRO.md §1.1]

## Done — archive

Moved verbatim to `docs/BACKLOG-ARCHIVE.md#done-archive` in the 2026-09-23 structural prune (groom pass 28) — nothing here is a live item, so it no longer needs to sit in every agent's context. One line per item, grouped by groom pass; commit SHAs and full evidence there.

## Changelog

- 2026-09-24 — **Groom pass 29 (backlog-groomer):** PICK-PROXY-COLLIDE-1,
  CONTRACT-PARITY-TEST-1, PERF-REAL-2, E2E-SHARD-COUNT-1,
  QA-CUBE-YIELD-SETTLE-1/FB-7 all CLOSED; CI green through `d3d0446`;
  6 items filed. See "Scorecard gaps" above and BACKLOG-ARCHIVE Done archive.
- 2026-09-23 — **Groom pass 27 (backlog-groomer):** e2e known-failures +
  shard-4 timeout root-caused and fixed (6+1 commits); F-6 and the
  gauge/panel lag CLOSED; 11 items filed. See "Scorecard gaps" above.
- 2026-09-23 — **Groom pass 26:** CRAFT-12/VEC3-DEDUP-1/CSP-1 CLOSED;
  adjacency tier 3 shipped; VISION re-scored twice; 5 items filed. See
  "Scorecard gaps" above for full detail.
- Passes 7-25: full reachability programme, CI hardening, SOLVE/PBT/SEL-2/
  ARC-BRANCH-1 clusters, Wave 3 close-out, Phase 5 flagship (SCRIPT-1),
  gauntlet F1/F2, CRAFT-13. Full detail: `docs/CHANGELOG.md`.
