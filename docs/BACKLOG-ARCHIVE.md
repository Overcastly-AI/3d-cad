# Backlog archive

Full-detail item narratives and closed-item records pruned from `docs/BACKLOG.md` in the 2026-09-23 structural prune (groom pass 28). Nothing is deleted: every entry below was moved verbatim (word-unwrapped, then re-wrapped) from a BACKLOG.md item. A live item in BACKLOG.md links here as `(history: docs/BACKLOG-ARCHIVE.md#<anchor>)`; a closed item's full original text lives here in full, with only a one-line record left in BACKLOG.md's own Done archive (also archived here, verbatim) or CHANGELOG.md.

<a id="closed-wave-flow-a1"></a>

### FLOW-A1

*kind: closed*

- [x] (P0, M) **FLOW-A1** — a size typed in the first frames after a draw is no longer discarded; the part no longer comes out silently wrong `2a90a92` [docs/design/AUDIT-FLOW-2026-09.md]

<a id="closed-wave-flow-a2"></a>

### FLOW-A2

*kind: closed*

- [x] (P0, L) **FLOW-A2** — Back, the breadcrumb and reload can no longer eat an unsaved sketch; guard + per-part draft `501331b` [docs/design/AUDIT-FLOW-2026-09.md]

<a id="closed-wave-w0rev"></a>

### W0REV

*kind: closed*

- [x] (P0, M) **W0REV modal-gate fix** — the blocking review finding (Enter on the exit prompt applied the armed draw dimension instead of saving/ leaving; `Ctrl+Z` leaked into the sketch behind the modal too) plus two more (a save in flight blurred the dialog and dropped its own focus trap; sketch drafts outlived sign-out) — one capture-phase `lib/modalGate.ts`, not a patch per listener `da98622` [W0 code review, 2026-09-12]

<a id="closed-wave-w0rev-3"></a>

### W0REV-3

*kind: closed*

- [x] (P1, S) **W0REV-3** — sketch drafts were never swept (`DRAFT_MAX_AGE_MS` checked only on read of that one key, so 50 parts left 50 buffers on disk indefinitely) and a full quota then degraded `auth/session.ts` silently, reading as "logged out on reload". **CLOSED groom pass 30 (`87daed6`+`caebc10`).** `auth/storage.ts` is now a leaf storage seam (key scan, quota detection); `sweepSketchDrafts` drops expired/unreadable drafts and caps the rest at 20 drafts / 2 MiB, oldest first, run at app start and (rate-limited) on writes; `writeEvictingDrafts` evicts oldest-first on `QuotaExceededError` and retries, never swallowing an unrecoverable failure (`state.persistError` now set + logged). A follow-up shipped the SAME pass: a new `packages/design` `Notice` primitive (in-flow, role=alert/status, row/stacked layouts) surfaces the failure — a dismissable top-bar strip on every page while `persistError` is set, and a pre-sign-in probe warning on `SignInPage` (a session-sized write through the same eviction path, removed after). New `session-storage-full.spec.ts` proves both notices are announced by role, reachable by `elementFromPoint`, and dismissed by a real click. [W0 code review, 2026-09-12]

<a id="closed-wave-flow-b2"></a>

### FLOW-B2

*kind: closed*

- [x] (P1, M) **FLOW-B2** — `K E R F C` bound for Sketch/Extrude/Revolve/ Fillet/Chamfer, the five verbs a hand reaches for most, which had no keys while seven rarer ones did `d5e936a` [docs/design/REDESIGN-ROADMAP.md W2]

<a id="closed-wave-flow-b1"></a>

### FLOW-B1

*kind: closed*

- [x] (P1, M) **FLOW-B1** — a solved sketch writes `EXTRUDE ⟨E⟩` on its own profile, closing the single largest measured flow gap (8 of the 15 hunts the audit recorded) `78aaa67` [docs/design/REDESIGN-ROADMAP.md W2]

<a id="closed-wave-flow-b3"></a>

### FLOW-B3

*kind: closed*

- [x] (P1, S) **FLOW-B3** — exactly one command-band tool wears the next verb after a build completes, gated by name rather than divination `fb63809` + `6097448` [docs/design/REDESIGN-ROADMAP.md W2]

<a id="closed-wave-craft-6"></a>

### CRAFT-6

*kind: closed*

- [x] (P1, M) **CRAFT-6** — the reference cube persists through plane-pick and sketch instead of unmounting with the view rail; facet clicks measured to steer the camera (41.85°/45.00° turns), the orthographic preference frozen for the duration of authoring `a340ff5` [docs/design/AUDIT-CRAFT-2026-09.md]

<a id="closed-wave-craft-1"></a>

### CRAFT-1

*kind: closed*

- [x] (P1, L) **CRAFT-1/2/3** — a filleted body now draws its edges (was 0 — the crease detector cannot see a tangent fillet; fixed off the tessellation's own face partition), a front/right/top orthographic view keeps its ground plane (was empty by construction, not a fade issue — a plane containing the view direction projects to a line under a parallel camera), and the origin triad is drawn at rest, dimmed `57d3bf8` [docs/design/AUDIT-CRAFT-2026-09.md]

<a id="closed-wave-x-p2-m-w2-code-review-fixes"></a>

### - [x] (P2, M) **W2 code-review fixes** — `? then E` opened E

*kind: closed*

- [x] (P2, M) **W2 code-review fixes** — `? then E` opened Extrude BEHIND the open key card and a focused button's Enter/Space was stolen by an `isTypingTarget` guard that does not cover buttons — the same "each half correct, wrong together" shape W0REV found, on `ShortcutSheet` (`6602ccd`, `activationKeyOwner` + a leak alarm; 22 pre-seam listeners named, not migrated — MODALGATE-MIGRATION-1 stays open below). Plus five smaller findings, all fixed: a chip's one-shot spent on an offer never drawn (`356ac66`); the chip's seed opening the wrong sketch on a raced refetch/undo (`46c8e6f`); a coverage floor that was vacuous — deleting its own row still passed the file it lived in 7/7, the real guard is elsewhere (`f317ac5`); `REPEAT_ROWS` keyed by bare `string` instead of the generated feature-type union (`6de8fdf`); the next-verb accent wearing "round it now" for an extrude built last week (`b7b7f12`); comments corrected to match (`bbb5ed3`). [docs/design/ REDESIGN-ROADMAP.md W2 review, 2026-09-13]

<a id="closed-wave-xwave-1"></a>

### XWAVE-1

*kind: closed*

- [x] (P1, M) **XWAVE-1 — a hidden body kept its brass feature outline; the branch tip was e2e-RED since `57d3bf8`, not a census artifact.** CRAFT-1's edge-overlay swap (crease detector -> real face partition) gave a latent hole in `ModelMesh`'s two edge-material paths enough ink to draw: hiding the plate left 667px of face-boundary outline floating in the void. DOM assertions all passed — only the GL ink was wrong. Fixed by deriving both paths from one `litFeatureFaces` precedence (`0c3e363`). [src: cross-wave QA, `docs/QA-REVIEW.md` 2026-09-13]

<a id="closed-wave-xwave-2"></a>

### XWAVE-2

*kind: closed*

- [x] (P2, S) **XWAVE-2 — the solve-proposal chip rendered OVER the reference cube and took its clicks.** The chip is the later `z-hud` sibling — 29% of the cube's seat taken including its exact centre, and a real click there opened Extrude instead of reorienting. `placeProposal` now tries four quadrants against `measureChrome`'s live `data-viewport-chrome` rects; a click landing on chrome no longer burns the one-shot offer (`76a214c`). [src: cross-wave QA, 2026-09-13]

<a id="closed-wave-xwave-3"></a>

### XWAVE-3

*kind: closed*

- [x] (P2, S) **XWAVE-3 — CRAFT-6 made the bottom-right corner dead to face picking.** The cube's `z-hud` layer sits above every pick mark by construction; 5 of 6 `plane-pick-face-N` marks and the surface pick itself went dead under it. The cube now yields its pointer while a pick is ARMED and takes it back the instant the pick ends; orbit/pan/zoom untouched (`d0a3190`). It deliberately does NOT extend to ordinary drawing — see **CUBE-SKETCH-OCCLUDE-1** below, the product decision this leaves open. [src: cross-wave QA, 2026-09-13]

<a id="closed-wave-xwave-4"></a>

### XWAVE-4

*kind: closed*

- [x] (P3, S) **XWAVE-4 — one Escape backed out two steps, in every configuration with two things to back out of.** Three uncoordinated `window` listeners, order decided by mount time. `lib/modalGate.ts` now declares one cascade (`drag > offer > mark`), run exactly one rung (`dbb09fb`). [src: cross-wave QA, 2026-09-13]

<a id="item-cube-sketch-occlude-1"></a>

### CUBE-SKETCH-OCCLUDE-1

*kind: item-story*

kind: question (product decision, not a defect). MEASURED: at a zoomed-in leg on a 1600x1000 frame, a point that is genuinely empty sketch space maps to (1519, 903) — inside the cube's seat — and `elementFromPoint` there returns the cube's canvas, not the scene's; a click lands on the cube and steers the view. THE STATE OF PLAY, so this is honest about what is already handled: `d0a3190` made the cube yield its pointer while a FACE PICK is armed (the plane-pick corner went from 5-of-6 marks unreachable to 0-of-6), counted through `armedPicks.ts`/`PickMark`. Sketch datum handles are drei `Html`, not `PickMark`, so during ordinary DRAWING `armedPicks` counts zero and the cube does not yield — `d0a3190` explicitly decided drawing never yields it, on the grounds that the sketcher's snap marks are not pick marks. So this is a genuine trade CRAFT-6 made ON PURPOSE (orientation matters MORE while drawing on a plane in space, not less), not an oversight, and the cost is that one corner of the sketch plane is not directly drawable. OPTIONS for a builder to weigh, not adjudicated here: (a) extend the pick-armed yield to drawing/snap gestures too; (b) shrink or inset the cube while sketching; (c) let a drag that STARTS on the scene (pointerdown outside the cube's rect) pass through even if it crosses the seat; (d) accept it and document the dead corner as a known limitation.

<a id="closed-wave-craft-8"></a>

### CRAFT-8

*kind: closed*

- [x] (P1, L) **CRAFT-8** — `<ParametricGauge>` extracted out of `ExtrudeDragHandle` (601 -> 88 lines), a four-way split forced because `packages/design` has no r3f; the shared foundation CRAFT-7/9/10/11 build on `4b0465d`. Review found three, all fixed: a gauge-override handle that churned a global listener once per drag frame (`b20e8ce`), the ask-queue's rules made deterministic — its old positive control had fired 2 of 12 runs (`fd1156a`), and `extrudeTrack`'s seam given the unit coverage the 36-case e2e suite could not provide (`730b2ae`) [docs/design/REDESIGN-ROADMAP.md W3]

<a id="closed-wave-craft-7"></a>

### CRAFT-7

*kind: closed*

- [x] (P0, L) **CRAFT-7 — CLOSED.** The extrude gauge is grabbable: reach 2 of 16 -> 16 of 16 sample points along its own projected axis; a real mouse drag from the shaft midpoint now moves the value where it previously left it at 40. Also: the zoom-aware snap (sampled once on arm and frozen thereafter — 40 wheel notches moved the shaft 3.86 -> 28.48 px/mm with the snap never updating), the spine drawn as a polyline rather than a chord, the readout became an input with digit capture, nested Escape, a leader on the tag `6864f82` + `e25f125`. **Its blocking review finding is now FIXED (`c9e037c`):** the px/mm scale divided a projected seat->arrow-TIP length by a WORLD seat->arrow-BASE length, so the original commit's own "14 px floor" was really ~11.9 px at depth 40 and ~9.7 px at depth 10 — every figure the commit reported was measured against the biased quantity. Fixed via `projectedSpineLength` in `gaugePose.ts`; the split snap-ladder floor (`majors >= 14px`, `pitch >= 7px`) that was gating on it needed no further change. Measured drawn pitch off the spine mesh's own `matrixWorld`, before/after, at two widths — 1600x1000: 2mm 12.07 -> 7.23px; 1280x800: 2mm 11.35 -> 7.15px (the 12.07 independently reproduces the reviewer's 12.08). `angularTrack` inherited and shares the same fix (relevant to CRAFT-10). `e56c9bc` separately re-derived the grip's e2e size tolerance as Blink's 1/64 px LayoutUnit quantum — the float32-ULP reading it replaced was only correct for x in [512,1024) and silently doubled past 1024. **CRAFT-9a/9b/10/11 are now unblocked and IN FLIGHT — see entries below.** Bisect note, kept for the record: `6864f82` (part of this item) has NO CI run of its own — pushed in the same event as `e25f125`, which fired one run keyed to the head commit — locally verified standalone (typecheck clean, 233 design + 2461 web tests) and tree-verified by `e25f125`'s green run, NOT CI-verified; keep that distinction if this commit is ever a bisect endpoint. [docs/design/REDESIGN-ROADMAP.md W3, §8 DIRECTION-W3-PROPOSALS.md]

<a id="closed-wave-x-p2-s-e2e-verdict-reporter"></a>

### - [x] (P2, S) **e2e verdict reporter** — a red shard named t

*kind: closed*

- [x] (P2, S) **e2e verdict reporter** — a red shard named the failing test and withheld the reason: `results[].error.message` was being dropped from the summary block `6043601`.

<a id="item-craft-intermittent-1"></a>

### CRAFT-INTERMITTENT-1

*kind: item-story*

(a) `rect-rigidity.spec.ts:281` — still open, unchanged; red on 2 of 5 recent CI runs, 31 local executions across seven stress axes gave zero failures, persisted constraint set byte-identical every time. (b) was `qa-cross-wave-0913.spec.ts:572` "the cube is a control again once the pick is over" (also seen at `:253`), filed as ONE intermittent because both lines shared a symptom (a cube-facet click not moving the camera) and both wandered their failure point. **They were not one cause.** `36360ae` (groom pass 27) root-caused the `:253` case (now "a click on the cube steers the camera and keeps the offer"): a fixed 800ms sleep read `data-camera-pos` before the click's camera ease had landed under load — a real assertion-timing defect, not an unreproduced race, fixed by polling the settle stamp the ease itself writes (`onSettle` → `data-view === "direction"`). 7/7 red under load before, 7/7 green after; two new assertions each seen to redden (dropping the click, or a precondition violated). This satisfies the ticket's own ACCEPTANCE for that half ("root-cause at least one to a specific race rather than filing it as CI is noisy") and means the "DELIBERATELY NOT touched" argument below did not hold for this half — the fix did not consume an evidence trail, it found the defect the trail was made of. **The `:592` sibling (renumbered from `:572`; "the cube is a control again once the pick is over" itself) still uses the SAME unfixed pattern** (`page.waitForTimeout(800)` then compares `data-camera-pos`) — filed separately as QA-CUBE-YIELD-SETTLE-1 (groom pass 27) rather than folded back in here, since it is now a known fix shape, not an open investigation. **Still applies to `rect-rigidity.spec.ts:281`:** shipping a synchronization fix without a reproduction would destroy the only evidence a future red run could hand a root-causer; that reasoning is now proven right in one direction (don't guess) and wrong in another (a suite that "produced zero reproductions" can still hide a provable, load-sensitive defect — the `:253` case reproduced 7/8 under load and 0/8 quiet, which the ticket's local stress runs may not have matched).

<a id="item-eslint-hooks-1"></a>

### ESLINT-HOOKS-1

*kind: item-story*

— `react-hooks` is not in `eslint.config.js` at all, repo-wide: no `exhaustive-deps`, no `rules-of-hooks`. That gap is why CRAFT-8's handle-churn defect (`b20e8ce`, a global listener re-armed once per drag frame) was invisible until a human review found it. Turning the rule on is its own change with its own blast radius — at least three deliberate latest-ref patterns in the viewport will need documented exemptions rather than fixes.

<a id="item-extrude-rail-escape-1"></a>

### EXTRUDE-RAIL-ESCAPE-1

*kind: item-story*

— Escape while the extrude rail's numeric field holds unsaved typed text closes the WHOLE command and discards it; pre-existing, not CRAFT-7's. FB-13-shaped inconsistency (CLAUDE.md: "a key that sometimes saves and sometimes discards"): the gauge's own cell (CRAFT-7) now nests Escape and behaves BETTER than the rail field showing the identical number, so the same value has two different Escape behaviours depending which control holds it.

<a id="closed-wave-craft-9"></a>

### CRAFT-9

*kind: closed*

- [x] (P1, M) **CRAFT-9a — CLOSED (`1f32a67`).** Fillet radius + chamfer distance gauges. Band preview on every picked edge — the fillet closes with the round's arc, the chamfer with the bevel chord. Reach 16/16 both verbs. Convexity is read from face CENTROIDS, not normals — a box's convex edge and a step's concave one present identical outward normals. Refuses rather than guesses on a closed edge with one planar face. [src: DIRECTION-W3-PROPOSALS.md §8.3/§9] agentType: frontend-builder.

<a id="closed-wave-craft-9-2"></a>

### CRAFT-9

*kind: closed*

- [x] (P1, M) **CRAFT-9b — CLOSED (`11a0906`).** Shell thickness + datum offset gauges. Shell draws the rim of the cavity the wall leaves — line-work deliberately: a ghosted solid would paint material exactly where the feature removes it. Both previews publish a QA stamp derived from the buffer handed to the renderer, never the value that produced it — needed TWO stamp functions, because a translating square has constant perimeter. **Open follow-up: `craft9b-gauges` contract-β is intermittent** — the rod springs back a step on release, 2/1/0 across runs on the base tree; see CRAFT-13 below. [src: DIRECTION-W3-PROPOSALS.md §8.3/§9] agentType: frontend-builder.

<a id="closed-wave-craft-10"></a>

### CRAFT-10

*kind: closed*

- [x] (P1, M) **CRAFT-10 — CLOSED (`7ecc480`).** Revolve sweep + draft angle on the 15°/5° ladder, **and it drew the revolve axis**, which did not exist in the viewport at all before this (a dropdown read "Y axis · through the origin" with nothing on screen). **Its own follow-up, `894c6f3`: the hit sleeve now follows the drawn ARC rather than its chord** — reach was 0/16 with the chord sleeve, worse than the 2/16 CRAFT-7 was raised to fix; found and fixed by this agent, which reverted its own out-of-territory file and escalated instead of leaving it. [src: DIRECTION-W3-PROPOSALS.md §9 CRAFT-10] agentType: frontend-builder.

<a id="closed-wave-craft-11"></a>

### CRAFT-11

*kind: closed*

- [x] (P1, M) **CRAFT-11 — CLOSED (`c0b5e5f`).** Pattern count + spacing gauges, two mounts on one feature. Ghost copies are simultaneously the preview and the count gauge's own stops; spacing keeps the tag, count carries `tag: "none"` because the ghosts ARE its reading — only one instrument may own the digits. **Follow-up `0c707b9`: the count gauge's seat left the frame** — its screen-space offset floor was written in world mm, so both `max()` floors selected their constant below 17 mm radius and stopped shrinking with the part while the camera-fitted frame kept shrinking. [src: DIRECTION-W3-PROPOSALS.md §9 CRAFT-11] agentType: frontend-builder.

<a id="closed-wave-x-p0-s-save-during-autosave"></a>

### - [x] (P0, S) **Save-during-autosave race — CLOSED (`d227843

*kind: closed*

- [x] (P0, S) **Save-during-autosave race — CLOSED (`d227843`).** A ~280 ms window in which the one control that ends a sketch (Save) did nothing, silently, while an autosave was in flight; the queue already existed one layer down, the disable is what made it unreachable. [src: Wave 3 cross-cutting finding, 2026-09-14] agentType: frontend-builder.

<a id="closed-wave-craft-12"></a>

### CRAFT-12

*kind: closed*

- [x] (P1, S) **CRAFT-12 — CLOSED (`7a15bea`).** A preview that would render outside the frame now triggers a bounded re-fit (outward-only, re-frame-never-re-orient, never mid-drag, once per command), measured 11 mm-part pattern ghosts 5.9% -> 100% visible. Hardening the gauge/camera e2e against a real bug the re-fit's own scope surfaced: `readProposal` unions the whole `command-layer` group including RESTING sketch ink, so a release can re-fit the camera when nothing is actually out of frame — filed AND CLOSED same day as **CRAFT-12-READPROPOSAL-1** (`5274bea`) below. [src: Wave 3 close-out finding 1, 2026-09-14; closed groom pass 26]

<a id="closed-wave-craft-13"></a>

### CRAFT-13

*kind: closed*

- [x] (P1, M) **CRAFT-13 — CLOSED (`b4e7821`).** Root cause was NOT the panel field sync — it was a P0: `894c6f3`'s per-segment hit sleeve made band count a function of the value being dragged (a 120° sweep carries 32 bands, 90° carries 24, keyed by index), so a shrinking arc sweep UNMOUNTED the band holding pointer capture mid-drag; Chromium emits no `lostpointercapture` for a removed capture host, so the drag froze permanently (measured live: value stuck at 90 after a grab near the seat, `data-grabbed` still "true" after mouse-up, bare-mouse movement then carrying the value 90→165 with no button held). Fixed by moving every pointer handler to the sleeve WRAPPER (lifetime = the gauge's, not the tessellation's) plus `if (event.buttons===0) endDrag()` at the top of `onPointerMove`, each verified by an independent negative control. The `craft9b-gauges` contract-β "intermittent" (rod springs back a step on release) is the SAME shape, confirmed rather than assumed: an unrelated `pointerleave` handler was incidentally flushing a stale `live` value via React commit, and the fix that correctly stops firing it exposed the settle that had always been required — both β cases now name it explicitly. Scope measured, not assumed: only revolve/draft (angular tracks) are affected; the other seven mounts build on `linearTrack`'s fixed two-point spine, one band always, re-run green. [src: Wave 3 close-out finding 2+3, 2026-09-14; closed groom pass 25] **FOLLOW-UP CLOSED groom pass 27:** the panel-field-sync lag this ticket ruled out as ITS cause was real on its own — seven of nine gauge-fed editors wrote their form from an EFFECT, one commit after the drag override, so a release could leave the drawn rod and the field one step apart for 2-4 frames. `3b7f9ad` fixed ExtrudeEditor (write during render, guarded by the override identity already applied); `357b91e` generalised it into `useGaugeFedForm`, adopted by all seven remaining editors. `gauge-release-sync.spec.ts` 12/12 after (was 3 failed/12), 0 disagreeing frames across a 10-drag timeline.

<a id="item-craft-14"></a>

### CRAFT-14

*kind: item-story*

kind: defect (systemic, audit first). `ToolButton` gives a consumer no way to distinguish "busy" from "gated" — both collapse to `aria-disabled` plus a swallowed handler.

<a id="item-craft-15"></a>

### CRAFT-15

*kind: item-story*

kind: defect, pre-existing (measured against a no-gauge control, not a W3 regression). PickMark/edge-overlay territory.

<a id="item-craft-16"></a>

### CRAFT-16

*kind: item-story*

kind: question (product decision). On a face the shell leaves open there is no wall along the centroid's normal — the wall is at the rim, in-plane, exactly where the preview already draws it. A rim seat would make the arrow and the outline one drawing.

<a id="item-craft-17"></a>

### CRAFT-17

*kind: item-story*

kind: DRY (CLAUDE.md non-negotiable) + latent test defect. `gaugeReach.ts` (CRAFT-9a) and `gaugeProbe.ts` (CRAFT-9b, since extended by CRAFT-10/11) both export `Point`/`projectedSpine`/ `gripCentre`/`reach` and the same sample count + reach floor (`SAMPLES`/`REACH_SAMPLES`=16, `REACH_FLOOR`=12). **Confirmed by code review (`451245c`): `894c6f3` gave the two `reach()` implementations different SEMANTICS** — `gaugeProbe.reachAlongTrack` samples along the drawn polyline (where the bands actually are); `gaugeReach.reach` samples the chord. Harmless today only by accident of who imports which (`gaugeReach`→`extrude-grip-reach.spec.ts`/ `fillet-chamfer-gauge.spec.ts`, both straight tracks where chord and polyline coincide; `gaugeProbe`→`craft9b-gauges`/`pattern-gauges`/ `revolve-gauge`). The first arc-gauge spec that imports the wrong module gets a false red reading "the sleeve is broken" instead of "I imported the other helper". `gaugeProbe.ts` is the survivor — it is already the one CRAFT-10/11 built on.

<a id="item-gauge-proportion-1"></a>

### GAUGE-PROPORTION-1

*kind: item-story*

kind: defect (visual craft, tolerance). MEASURED: at pitch <= 0.5 mm, or on a very large seat (a 500 mm profile draws a 2.42 mm rod against a 1 mm `majorStep`), the rod is fatter than the graduation spacing and no arm rule fixes it — the mark is inside the thing it graduates, the same shape CLAUDE.md's screenshot-gate incident documents (a ladder can be correctly sized by its own rule and still invisible). CRAFT-7's per-class spacing bound (`majors >= 14px`, `pitch >= 7px`) closed the one case it was measured against (2 mm ladder, 0.97 mm rod) and does not generalize to either extreme above.

<a id="item-formatangle-migrate-1"></a>

### FORMATANGLE-MIGRATE-1

*kind: item-story*

kind: DRY (CLAUDE.md non-negotiable). CRAFT-8 added `formatAngle` to `packages/design/src/units.ts` beside `formatLength`, deliberately WITHOUT migrating the existing call sites — converging `apps/web/src/measure/geometry.ts`, `apps/web/src/features/revolve.ts` and `apps/web/src/features/hole.ts` crosses three territories, so CRAFT-8 filed it rather than doing it.

<a id="item-imperial-ladder-1"></a>

### IMPERIAL-LADDER-1

*kind: item-story*

kind: question (needs a measurement, not yet a decision). The ladder-as-snap-stops decision made the METRIC ladder a decade series (5 -> 2 -> 1 -> 0.5), but `SNAP_MM.in = 25.4/32` is a named, human step (a 32nd of an inch) and a decade ladder over it would replace that with a value nobody says out loud. The W3 direction's stated instinct is a **binary** series (1/32, 1/16, 1/8, 1/4, 1/2, 1 in) under the same screen floor — explicitly NOT decided, because no inch document was measured this pass.

<a id="item-gauge-touch-1"></a>

### GAUGE-TOUCH-1

*kind: item-story*

kind: QA (not yet examined, flagged rather than guessed). The 24 px grip meets WCAG 2.2 SC 2.5.8 and CRAFT-7's hit sleeve is >= 12 px, but every reach measurement behind the wave — all nine mounts across all seven verbs — was mouse-driven, at 1280x800 and 1600x1000 only; nobody has put a finger on any of these instruments.

<a id="item-kernel-helical-sweep"></a>

### Kernel: helical sweep -> threads/gears (G1)

*kind: item-story*

CLOSED groom pass 32 (`d823af9` + review fixes `debd5b7`/`87d099f`/`43ab526`/`cbc5720`, build `000cc4d`). Twisted extrude ships: geometry-QA independently verified it twice (`a83d53a`, `e686107`) against a closed-form gear/screw-motion truth — volume 36470.392 vs. 36470.374 analytic (+4.7e-7 relative), twist to 5 dp, 29/29 stress cases byte-deterministic, STEP round-trips at <=4.4e-9 mm^3. The ruled-loft workaround's -0.61%-volume/0.11mm-tooth-error gap is now avoidable. Four residuals the same QA pass found are filed separately (TWIST-VOLUME-INTEGRATOR-1, TWIST-EXTRUDE-UI-1, TWIST-TESSELLATION-PERF-1, TWIST-ORIENT-INSIDE-OUT-1, FEATURE-TREE-ROW-CLIP-1).

<a id="item-sketch-typed-point-1"></a>

### SKETCH-TYPED-POINT-1

*kind: item-story*

CLOSED groom pass 32 (`e4d5805`). A sketch point accepts a typed X/Y while placing (FB-16's typed-dimension idiom); `setSnapStep` gained a UI caller so the grid step is configurable.

<a id="item-sketch-view-reset-1"></a>

### SKETCH-VIEW-RESET-1

*kind: item-story*

CLOSED groom pass 32 (`fc5e840`). A sketch edit (constraint/dimension/trim) no longer re-frames the zoomed sketch view; an explicit Fit/Home still does.

<a id="item-sketch-glyph-hittest-1"></a>

### SKETCH-GLYPH-HITTEST-1

*kind: item-story*

CLOSED groom pass 32 (`09cb3d8`). A click on a constraint/dimension label no longer lands at the canvas corner.

<a id="item-sketch-entity-delete-1"></a>

### SKETCH-ENTITY-DELETE-1

*kind: item-story*

CLOSED groom pass 32 (`851d6ef`), same commit as G12's stuck Undo (UNDO-BUSY-LABEL-1). Delete/Backspace on a selected sketch entity removes it and every constraint that named it, as one undo step; two independent trim-dropping causes fixed in the same investigation (a stale request nonce, and a trimmed curve keeping its old-shape constraints).

<a id="item-sketch-arc-snap-gap-1"></a>

### SKETCH-ARC-SNAP-GAP-1

*kind: item-story*

CLOSED groom pass 32 (`f57111d`). The sketcher marks open profile ends and names the gap — the ticket's "explicit open-profile warning before the feature error fires" branch.

<a id="item-session-ttl-refresh-1"></a>

### SESSION-TTL-REFRESH-1

*kind: item-story*

CLOSED groom pass 32 (`cd6baed`+`3c18833`, review fixes `9a780b4`/`2d0df47`/`3cb432f`/`fdcae20`/`82be0e4`/`9336165`, docs `6f6afb7`/`a449f85`/`1719d0a`). Sliding sessions with rotating refresh cookies replace the 1-hour hard expiry.

<a id="item-undo-busy-label-1"></a>

### UNDO-BUSY-LABEL-1

*kind: item-story*

CLOSED groom pass 32 (`851d6ef`), same root cause as SKETCH-ENTITY-DELETE-1/G7: a stale request nonce (every geometry request took `previous.nonce + 1`, but success cleared the request to null, so the 2nd edit of a session restarted at 1 and never landed, leaving Undo stuck on "Finishing the last edit...").

<a id="scorecard-gaps-history-25-19"></a>

### Scorecard gaps — groom passes 19-31 narrative

*kind: scorecard-history*

- **Groom pass 31 (2026-09-24, backlog-groomer) — the helical-gear product
  test (`docs/qa/helical-gear-2026-09-24.md`, tested at `95dd9cd`), first
  real complex-part test since the 2026-09-16 gearbox audit.** 16 ranked gaps
  filed/reconciled (Ready: SKETCH-TYPED-POINT-1/VIEW-RESET-1/GLYPH-HITTEST-1/
  EXPR-FUNCTIONS-1/ENTITY-DELETE-1/ARC-SNAP-GAP-1/SESSION-TTL-REFRESH-1;
  Next: SKETCH-DIM-POINT-DISTANCE-1, CHAMFER-FACE-LOOP-SELECT-1,
  PATTERN-LOFT-EVAL-COST-1, UNDO-BUSY-LABEL-1, STEPIMPORT-PART-NAME-1; Later:
  SKETCH-CIRCLE-RUBBERBAND-TYPE-1, LOFT-EDITOR-PRESELECT-1,
  CHAMFER-ERROR-COPY-1, LOFT-BSPLINE-OPTION-1). The helical/twisted-extrude
  kernel item and the session-TTL item were IN FLIGHT with other agents, not
  Ready (both closed pass 32). STEPNAME-1/1B/2 closed and removed
  (`5220841`+`95dd9cd`). Proposed VISION.md scorecard changes (judgment call
  for the vision-steward): Sketching & constraints (➖) gains four more
  live-app-measured residuals in the same shape as its existing "no
  Fit/Home" finding (view reset after a constraint/edit, glyph click
  mis-mapping, no entity delete, arc-snap gap); Part modeling (➖) gains a
  first live measurement of the ruled-loft-only helix gap (-0.61% volume /
  0.11mm tooth error); Extensibility/scripting (➖) gains a positive data
  point (the script route built the same part correctly in 6.2s and
  re-derived a helix edit in 5-9s).

- **Groom pass 30 (2026-09-24, backlog-groomer) — CI-confirmed green through
  `9c21801` (all three workflows); W0REV-3, MEASURE-LABEL-PITCH-1, PERF-REAL-1
  and the reused-id PERF-REAL-3 (overlay cache-key collision) all CLOSED.**
  `87daed6`+`caebc10` sweep sketch drafts (expiry then oldest-first, ≤20
  drafts/2 MiB) and surface a full-quota session write failure to the user via
  a new `packages/design` `Notice` primitive, instead of a silent "logged out
  on reload". `dc49558` gives Measure a labelled centre-to-centre reading
  distinct from the raw minimum-distance one (25.0mm pitch vs 17.0mm min,
  verified on a known plate) plus per-target identity in the readout.
  `a785d84`+`ac568b7`+`fafbf78`+`14838cb` replace the brute-force per-face
  raycast with a BVH (22ms→0.2ms/ray, 0 mismatches over 19,800 rays) and fix a
  real bug the speed-up exposed (the part rig's auto-fit was posing the
  camera while the sketcher owned it); on `gearbox-11752`, arm→prompt
  42-48s→~11s, click→sketch-on-face ~31s→8-15s, mark settle never→~34-36s.
  `496d275`+`989349c`+`9c21801` (reusing the id PERF-REAL-3 for a DIFFERENT
  defect than the still-open mesh-payload PERF-REAL-3) took `record_history`
  out of the rebuild-cache key so a face pick after an evaluate is a cache
  hit, not a guaranteed miss (overlay after evaluate 8.8s→~2.1s via the
  gateway; recording costs 0.06-1.6% of a cold rebuild). Filed 9 items
  (GAUNTLET-BROWSER-CI-1, EDGE-BAND-RAYCAST-BVH-1,
  OVERLAY-CACHE-HIT-RESIDUAL-1, STEP-IMPORT-CACHE-1, GAUGE-POINTERUP-FLAKE-1,
  E2E-DURATIONS-MANIFEST-1, MEASURE-CIRCLE-STRAIGHT-EDGE-1,
  LINEAGES-DOCSTRING-STALE-1, SESSION-EXPIRED-NOTICE-1). No scorecard row
  flips this pass; Selection & picking's PERF-REAL-1 upper bound is now
  stale in VISION.md's favour, a vision-steward re-check is owed.

- **Groom pass 27 (2026-09-23, backlog-groomer) — every known e2e failure on
  the branch root-caused and fixed LOCALLY; CI verification owed.** F-6
  closed on measurement (hole CREATE veto tried then withdrawn); the
  gauge/panel one-commit lag generalised into `useGaugeFedForm` across all
  nine gauge-fed mounts; F-11 (Fit while sketching) shipped with its own
  same-pass regression fixed. 11 items filed (QA-CUBE-YIELD-SETTLE-1,
  FILLET-GAUGE-FPS-FLOOR-1, E2E-SHARD-COUNT-1 among them), one
  (CONSTRAINTS-GLYPH-1280-1) closed same pass. No scorecard row flip.

- **Groom pass 26 (2026-09-23, backlog-groomer) — 29-commit debt reconciled
  (largest batch yet at the time); `e2e` found RED on the tip.** CRAFT-12,
  VEC3-DEDUP-1 and CSP-1 closed; adjacency tier 3 closed the audit's
  `SUBSHAPE_UNRESOLVED` collapse for straight edges (curved neighbours left
  as an explicit residual). VISION.md re-scored twice: no capability row
  above parity, Performance ➖→❌. Filed PICK-PROXY-COLLIDE-1,
  MEASURE-LABEL-PITCH-1, EDGE-RESOLVE-WARN-1, INSTANCEOF-THREE-1;
  CRAFT-12-READPROPOSAL-1 filed and closed same pass.

- **Groom pass 25 (2026-09-15, backlog-groomer) — Phase 5's flagship SHIPPED; the gauntlet found and fixed a wrong-volume P0-adjacent defect; CRAFT-13 closed.** 25 commits landed since pass 24's `87f4de4`, ALL carrying `Doc-tick: groomer` — the largest debt batch yet (prior largest was 12), reconciled in full this pass. Highlights: **SCRIPT-1 CLOSED** — the public Python scripting API (`import loft`) shipped, proven two-path-identical to a browser-driven build (12/12 facts, byte-equal STEP/STL hashes), then split into `packages/loft-wire` (a script's venv: 33 deps → 15). **F1/F2 CLOSED** (geometry-qa's gauntlet, `0e3cc35`+`f7cd483`) — real-part volume was wrong by 1.49e-3 (1.58 L on a 1.07 m³ robot; no golden could ever fail for this — the bias is exact on planes/quadrics) and `mesh_glb_id` was non-deterministic across cache state; both fixed with a new golden and a structural gate. **CRAFT-13 CLOSED** (`b4e7821`) — root cause was a P0 (an arc gauge's pointer-capture host could unmount mid-drag) plus an unstated settle masquerading as an intermittent; both fixed with a negative-control-verified two-part change. **Air-gap claim FIXED** (`725bc4b`) and **self-host path now reaches the app** (`977f492`+`093dfc1`, a `web` service existed nowhere before), each shipped alongside a CI guard that had manufactured its own failure (root-owned nginx pidfile; a job-level `${{ runner.temp }}` rejecting the whole workflow at zero jobs) — both now closed with dedicated gates. **Scorecard freshness gate shipped** (`b1bb1b6`) — the mechanical check VISION.md itself proposed after the 19-day-stale Assemblies incident; advisory only, and a code review found it has no PENDING deadline (filed SCOREFRESH-PENDING-1). **DIRECTION-ASSEMBLIES.md filed** (`21a039f`, vision-steward) — four items (PERF-ASM-1/PICK-ASM-1/BOM-ASM-1/FLOW-ASM-1) now on the board, BOM-ASM-1 replacing the old flat "RECURSIVE BOM" entry. A same-day code review (`451245c`, `docs/CODE-REVIEW.md`) found two P0s (both fixed same batch: the `delete_feature` 422 and the CRAFT-13 arc-drag P0) plus five P1s/P2s now filed: CONTRACT-PARITY-TEST-1, VEC3-DEDUP-1 (four divergent Vec3 helper copies, already diverged in behaviour — a real NaN-propagation risk), SCOREFRESH-PENDING-1 (above), plus two P2 process notes folded into existing items (CRAFT-17, gen-check's verdict line). **Scorecard gaps flagged for the vision-steward (not mine to score):** Extensibility (was ❌, PENDING on SCRIPT-1) now has a two-path-proof landed — re-score due; Free & unlimited / Your data-your-files (both PENDING on the air-gap/self-host audit) now have `725bc4b`+`977f492`'s evidence to score against; Performance (PENDING on the gauntlet) now has the gauntlet's numbers, and they are bad — score in whichever direction the evidence points, do not assume the direction. Full ranking of what the gauntlet found: ROADMAP "Current focus" — interaction cost (55-73s/face pick, 46-51s/edit) ranks first, ahead of the mesh payload and the round-trip drift. **Board queue length: 183 → 201 open items** (`grep -c '\[ \]'`-counted) — this pass closed 3 headline items (SCRIPT-1, F1+F2, CRAFT-13) and filed 16 (four PERF-REAL/gauntlet items, four code-review P1/P2 items, four Assemblies-wave items from DIRECTION-ASSEMBLIES.md, and four smaller process items — GEN-CHECK- VERDICT-1, DOCS-EXPLORER-1, CSP-1, AREA-INTEGRATION-1) net of one removed duplicate (the old flat-BOM entry BOM-ASM-1 replaces) — a filing-heavy pass, consistent with "a batch this large surfaces more findings than it closes." ROADMAP "Current focus" reconciled to match; Phase 5 marks the scripting API ✅, MCP server remains the open surface.

- **Groom pass 24 (2026-09-15, backlog-groomer) — Wave 3 CLOSED.** CRAFT-9a (`1f32a67`), CRAFT-9b (`11a0906`), CRAFT-10 (`7ecc480`+`894c6f3`) and CRAFT-11 (`c0b5e5f`+`0c707b9`) all ticked CLOSED, plus a cross-cutting Save-during-autosave fix (`d227843`). Nine gauge mounts now ship across seven verbs, every one with a live preview. Filed six new items from the wave's own findings (CRAFT-12..17: camera never re-fits on a preview, gauge/panel desync possibly sharing a root cause with the craft9b-gauges contract-β intermittent, `ToolButton` disabled-vs-busy audit, 3/12 pre-existing unreachable edge points, the shell rim-vs-centroid seat decision, `gaugeReach.ts`/`gaugeProbe.ts` DRY convergence); GAUGE-TOUCH-1 updated to cover all nine mounts and explicitly noted as a still-open W3-exit QA gate even though the wave itself is closed on the board this pass — a stated tension, not a silent resolution. CRAFT-9c stays Ready, now first in line. **Phase 5 (agent-native & extensibility) opened** — the public Python scripting API is in flight (see ROADMAP "Current focus" for the full rationale: it and the MCP server are one architecture flipping two ❌ scorecard rows, Extensibility + Agent access). Doc-tick debt measured: **12** commits since the last `docs(board)` commit (`bd1e05a`), none touching ROADMAP/BACKLOG — larger than pass 23's 4, all from Wave 3's remaining four gauge mounts landing in worktrees while two builders stayed live; reconciled in full this pass. **Board queue length: 183 open items (`grep`-counted), roughly flat from 181 last pass** — this pass closed 4 (CRAFT-9a/9b/10/11) and filed 6 (CRAFT-12..17), consistent with the wave-close pattern: findings surface fastest right at the end. No scorecard row flips this pass (flow/craft items; Phase 5's own flips are ahead of us, not behind). ROADMAP "Current focus" reconciled to match.

- **Groom pass 23 (2026-09-14):** CRAFT-7's blocking finding fixed and closed; CRAFT-9a/9b/10/11 unblocked and dispatched. Filed GAUGE-PROPORTION-1, FORMATANGLE-MIGRATE-1, IMPERIAL-LADDER-1, GAUGE-TOUCH-1. Full detail: `docs/CHANGELOG.md`.

- **Groom pass 22 (2026-09-14):** board was stale (CRAFT-7 listed planned after shipping); ticked CRAFT-7/8, filed ESLINT-HOOKS-1, EXTRUDE-RAIL-ESCAPE-1, CRAFT-INTERMITTENT-1. Full detail: `docs/CHANGELOG.md`.

- **Groom pass 21 (2026-09-13):** cross-wave QA (`debfea2`) found one regression + three collisions, all seven fixes ticked; filed CUBE-SKETCH-OCCLUDE-1. Full detail: `docs/CHANGELOG.md`.

- **Groom pass 20 (2026-09-13):** reconciled the wave log onto BACKLOG; filed six items (MINIO-LICENSE-REVIEW-1 + five more). Full detail: `docs/CHANGELOG.md`.

- **Groom pass 19 (2026-08-29):** CI-4's original question ANSWERED (shard 3/4 was structurally overloaded, not systemic instability); K2, PBT-1, SOLVE-CRASH-1, ARC-DEGENERATE-1 all closed. Full detail: `docs/CHANGELOG.md`.

<a id="item-perf-real-1"></a>

### PERF-REAL-1

*kind: item-story*

kind: defect (interaction cost, frontend/viewport). MEASURED by `just gauntlet` on `gearbox-11752` (1018 faces): arm face-pick → prompt visible 40.8s/30.0s (two runs); click → prompt cleared 31.6s/24.6s — 55-73s total against 0.6s to reach "Pick a plane" in the first place. Pick-node census: 452 DOM overlay nodes for one part, 17.5s to settle them (bit-identical structural counts across two runs at different load, which is what makes this a real cost rather than an artefact). Ranked #1 by "what a user feels" in `docs/GEOMETRY-QA.md`'s gauntlet entry — nothing else on that list matters if the tool cannot be touched. **PARTLY ADDRESSED this pass by `9083f0a` (found while landing PickMark's depth `instanceof` fix, not dispatched against this ticket directly): drei's `Html` was calling `ReactDOM.createRoot` PER pick mark, so 452 marks were 452 independent React roots — ~13s of main-thread script, a hang rather than a slowdown. Now one portal host, one root, one per-frame projection pass: 3.5x faster per mark in a real browser and FLAT instead of super-linear in N (measured at N=113/452/904, all ~0.30ms/mark against 1.08-1.32ms before).** The 55-73s / 17.5s-settle figures above are NOT re-measured against this fix and are now an UPPER BOUND — `docs/VISION.md`'s Selection & picking row says so explicitly.

**CLOSED groom pass 30 (`a785d84`+`ac568b7`+`fafbf78`+`14838cb`).** Re-measured
on the same `gearbox-11752` gauntlet fixture, production bundle, software GL:
the surface/face pick raycast (`Mesh.raycast`'s triangle loop, ~22ms/ray on
the real mesh, ~4,600 rays/pose at 24/frame) was the dominant cost, not the
pick-mark render `9083f0a` already fixed. A per-geometry triangle BVH
(`pickBvh.ts`) replaces the brute-force scan for surface/face raycasts:
22ms->0.2ms/ray, 0 mismatches against brute force over 1,200+19,800 rays
(landing commit + review). After: prompt 10.5s (was 42.3s), first mark 20.8s,
seats settled 34.0s (was never-settling at 158 frames/666s), click->sketch
on face 8.2s (was 30.7s). `ac568b7` added a real browser-leg gauntlet spec
(`apps/web/e2e/gauntlet/`) proving the numbers outside the in-process
harness. `fafbf78` found and fixed a real product bug the speed-up exposed:
the part rig's auto-fit was posing the camera (an instant re-fit on mesh
change) while `SketchCameraRig` owned it — a race that used to lose because
the slow raycast kept the sketcher's own ease in flight long enough to win;
made deterministic by a new regression asserting <0.01mm drift (was
17.46mm, 2/2). `14838cb` closed 5 review findings (first-frame-after-idle
budget bug, unsorted material-group fallback, geometry-dispose tree
rebuild + memory drop 90MB->44MB peak, a DRY raycast-oracle merge, an
expanded hit-field/edge-case pickBvh test suite) — each seen red under its
own mutation. Edge-band raycast (still a full segment scan) and edge-pick
timing on a real part were NOT measured this pass — refiled as
EDGE-BAND-RAYCAST-BVH-1. The gauntlet browser leg is not yet wired into
`just gauntlet` — refiled as GAUNTLET-BROWSER-CI-1.

<a id="item-perf-real-2"></a>

### PERF-REAL-2

*kind: item-story*

kind: defect (perf, kernel). MEASURED at 250 features: repeat 235ms, append 2444ms, edit feature #249 (near the end) 45955ms, edit feature #3 (near the start) 48449ms, cold rebuild 51741ms — an edit costs 89-108% of a full cold rebuild WHEREVER it sits in the tree, confirmed load-invariant by re-measuring at a different load average (the edit/cold RATIO moved from 0.89/0.94 to 1.02/1.08, i.e. it did not improve under less contention). `rebuild_cache.py` already documents that it does not serve a mid-tree edit; this gives the gap a number on a realistic part: ~46-51s for a one-parameter change. Ranked #1 (tied with PERF-REAL-1) in `docs/GEOMETRY-QA.md`'s gauntlet ranking.

**CLOSED groom pass 29 (`09416c6`+`4fcb108`+`560eab1`+`8e9e5c8`+`8077ede`+
`83e3c67`).** A checkpoint ladder forks state at every 8th feature boundary;
geometry-qa independently re-measured edit #249 at 34.1/34.0s -> 1.85/1.87s
(18.5x, both directions). Edit #3 is an explicit, accepted floor (+4% over a
cold rebuild, the fork tax) — no ladder can buy back an edit whose every
later feature must re-run; refiled as PERF-REAL-2B (dependency-aware
evaluator). Both caches this feature touches are now bounded in heap BYTES,
not a proxy count (faces / entry count), after geometry-qa found the
original bounds priced 6-16x low on real NURBS parts: the ladder at 64 MiB
(`8e9e5c8`, GQA-LADDER-1/2/3 all fixed in the same commit) and the frontier
at 128 MiB (`8077ede`) with one live oversize checkpoint held alone rather
than refused, so a >128 MiB part's own repeats stay cache hits (`83e3c67`).
Full geometry suite green throughout (3160-3180 passed each commit); every
new gate mutation-verified red first.

<a id="closed-ready-vec3-dedup-1"></a>

### VEC3-DEDUP-1

*kind: closed*

3. ~~**VEC3-DEDUP-1**~~ — **CLOSED (`4549da8`, groom pass 26).** See closure note below, after this numbered list.

<a id="item-contract-parity-test-1"></a>

### CONTRACT-PARITY-TEST-1

*kind: item-story*

— the call-parity test `packages/loft-script/src/loft/transport.py` documents as closing the loop does not exist. kind: defect (missing gate, not a live bug — SCRIPT-1 follow-up). `transport.py:148-156` states the model passed to `call()` is never looked up from `operation.response_model` "on purpose ... the contract-parity test closes the loop by asserting the two agree for every call site" — but `test_contract_parity.py`'s five tests only assert that `response_model` NAMES resolve to contract components, never that any `transport.call(op, Model)` site passes the Model the contract declares for that op. AST-walking the 16 call sites by hand today finds 0 mismatches, so this is not yet a live defect — but Pydantic's `extra="ignore"` default means a structurally-compatible WRONG model validates silently (CLAUDE.md's own documented trap), and the docstring claims a guarantee nothing enforces.

**CLOSED groom pass 29 (`647f939`).** Expected set now derived independently
from `gateway.openapi.json` (method/path/response/request/params), not from
the generated table the call sites import — 0 disagreements over 86
operations. Adds a >=16-site census floor per declared root module, the
helper axis (call/call_none/call_bytes chosen from the contract's success
response), and an import-alias check. 6 negative controls, each reverted
after reddening the new test. Confirmed with the author: `part.py:317`
(`delete_feature`'s `call_none`-on-a-DELETE-that-returns-a-body shape) was
NOT deliberate — it was the bug `43c03a1` already fixed 25 minutes after this
ticket was filed, moving it to `call(..., FeatureTreeResponse)`.

<a id="item-minio-license-review-1"></a>

### MINIO-LICENSE-REVIEW-1

*kind: item-story*

— MinIO is AGPL-3.0 and has no entry in `docs/LICENSING.md`; needs a human/licensing-custodian decision, not an automated one. kind: question (licensing/compliance). `docs/RESEARCH.md` §8: "Forbidden: GPL/AGPL dependencies. Reviewers enforce this." `docs/LICENSING.md` carries 72 entries and none for MinIO. Orchestrator's own reading, NOT adjudicated here: likely NOT a violation as shipped today — MinIO runs as a separate process over the S3 HTTP API, we do not link, modify or redistribute its bytes, so it reads as aggregation, and AGPL §13's network clause binds whoever DEPLOYS it. But §8's own amendment holds "`docker push` is what makes us a distributor," and `bd58416` (2026-09-13) had to repoint our compose pins because MinIO Inc. withdrew ALL binary images and moved to source-only distribution — so if upstream never publishes binaries again, the replacement path may require building the image ourselves, which is the scenario that amendment exists for.

<a id="item-flow-journey-gap-1"></a>

### FLOW-JOURNEY-GAP-1

*kind: item-story*

— the canonical part-creation journey does not exercise the shortcuts W2 shipped, so `scripts/check-flow-cost.py`'s headline (30 gestures) is unchanged and the wave's win is unmeasured on the path anyone actually walks. kind: capability/measurement. FOUND: the script's only "no API shortcuts" journey is `full-flow.spec.ts` (register → part → sketch → extrude → edit → export), which still drives the toolbar for every verb — K/E/R/F/C (FLOW-B2), the solved-sketch Extrude chip (FLOW-B1) and the next-verb accent (FLOW-B3) are all reachable from that same journey and none are used. WHY IT MATTERS: W2 made a shorter path EXIST; nothing made it the path the measurement — or a new user — takes, so the metric the loop steers by cannot see whether the wave paid off.

<a id="item-gridminor-tonemap-1"></a>

### GRIDMINOR-TONEMAP-1

*kind: item-story*

— grid minor lines are ~invisible, and the direct fix reddens a neighbouring gate. kind: defect (visual craft, cross-gate tension). FOUND (CRAFT-1/2/3 agent, correctly reverted rather than shipped): `gridMinor` (#232E3C) reaches the canvas at ~(21,26,33), within 3 luminance units of the background, because the tone mapper re-grades it before the pixel lands. Un-tone-mapping the grid line fixes the contrast but reddens `part-visibility.spec.ts`'s ghost census (203 against a 131 ceiling): the canvas is premultiplied-alpha and drei's grid shader emits straight colour, so the readback amplifies grid pixels past the specular threshold used to detect a ghosted body. NOT in CRAFT-2's scope (that item was the ortho ground plane, already shipped).

<a id="item-modalgate-migration-1"></a>

### MODALGATE-MIGRATION-1

*kind: item-story*

— `modalGate`/`useModalLayer` is built as "one gate, not a patch per listener" but still has only TWO registrants against 22 named holdouts. kind: defect (systemic, incomplete rollout — same shape as REASON-GATE-1's "15 of 16 editors" finding). **PROGRESSED, not closed, since filed:** `6602ccd` (W2 review) gave `ShortcutSheet` (the key card) a registration — the exact "`? then E` opens Extrude behind the card" defect this ticket predicted — plus an `activationKeyOwner` seam so a focused button's own Enter/Space is no longer stolen, and a leak alarm that fires the instant a key reaches the workspace while an `aria-modal="true"` element is on screen. `modalGate.audit.test.ts` now WALKS `apps/web/src` for raw `addEventListener("keydown")` and names every file not in its table: 22 pre-seam listeners across 12 files, recorded but not migrated. That audit test is the acceptance-criteria enumeration this ticket asked for — read it for the remaining list rather than re-deriving one.

<a id="item-axislabel-ortho-1"></a>

### AXISLABEL-ORTHO-1

*kind: item-story*

— `origin-axis-label-{X,Y,Z}` are absent from the DOM in front-orthographic when datums are enabled, though present and visible in the default view. kind: defect. Found during CRAFT-1/2/3 verification; view-dependent, uses drei `Html`, not caused by that diff and not yet root-caused.

<a id="item-viewfront-ortho-decision-1"></a>

### VIEWFRONT-ORTHO-DECISION-1

*kind: item-story*

— `view-front` (and the other named views) silently switch the camera to orthographic; decide this on purpose rather than by inheritance. kind: question (product decision). `viewCommands.ts`: the first named view the modeler asks for switches projection — so pressing `1` was, until CRAFT-2 landed, the fastest route into the empty-ground-plane bug (front/right/top ortho had no ground at all). CRAFT-2 fixed the symptom; this ticket is whether a named-view key SHOULD carry a projection change as a side effect, or whether view and projection should be independent controls (as CRAFT-6 already argues for the cube vs. the projection control during authoring, for a related reason).

<a id="item-craft-9"></a>

### CRAFT-9

*kind: item-story*

Hole depth + Ø gauges, the only `companion` two-cell gauge in the wave. **Deliberately NOT dispatched alongside CRAFT-9a/9b/10/11** — DIRECTION-W3-PROPOSALS.md §8.3 sequences it last, once the tag/`companion` shape has settled from the other four, now all CLOSED (CRAFT-7's own follow-up found `companion` had shipped narrowed to `Pick<GaugeCell, "tagLabel"|"value">`, losing the per-cell `track` §6.1 specified for a mixed-unit pair — fine for hole today since depth and Ø are both mm, but the shape this item inherits should be checked once CRAFT-9a/9b/10 have exercised it). `linear` track, anchor on the hole axis.

<a id="item-pick-proxy-collide-1"></a>

### PICK-PROXY-COLLIDE-1

*kind: item-story*

kind: defect (selection, frontend). MEASURED with `elementFromPoint` at each proxy's own centre, on a real gearbox-housing part: Measure draws **110 proxies (66 edges + 44 vertices) at once, 48 of them (44%) unreachable at their own centre** — each other's collisions; Fillet's `fillet-radius-sleeve` (88x17) lands exactly on `edge-pick-4`, so the gauge that appears when you pick covers one of the things you pick; Hole's inner-wall proxy sits 9px from the outer wall's twin and resolves to it; Shell's `shell-face-1` (bottom face) is drawn at a screen point inside the visible FRONT wall, so clicking the middle of the front wall opens the bottom and the panel reports "1 face open" with no warning. The GL raycast rescues most picks (decided in 3D, not by the DOM stack), but the DRAWN markers are what a user aims at and they lie about what is under them.

**CLOSED groom pass 29 (`9404cb1`+`b9d2a78`).** Real occlusion/publishing
root causes, one per symptom: edge marks published stale (`working`/
`published` shared one array); the settled stamp fired before the seat
reached the screen; face marks had no occlusion oracle (`useSurfaceMarkBurial`
now asks the pick surface itself); a buried mark drew nothing (now a dashed
`BuriedMark`); a gauge covered the mark that spawned it (`GaugeKeepOuts`).
Census (47 marks, 1280x800): before 7 live-but-buried + 3 faces stealing a
visible wall + gauge blocking its own pick; after 0 lies, 13-24 reachable per
class, un-pick by a real click restored. `b9d2a78` fixed 3 import-remix specs
that had relied on a buried mark being clickable (a real defect: picking a
face the camera shows FACING AWAY).

<a id="item-measure-label-pitch-1"></a>

### MEASURE-LABEL-PITCH-1

*kind: item-story*

kind: defect (product/measure). MEASURED: picking two adjacent Ø8 holes of a pattern whose centre-to-centre pitch is **25 mm by construction** reads back `DISTANCE 17 mm` (25 − 8, the minimum circle-to-circle distance) with no label saying "minimum" and no centre-to-centre / diameter / radius option on a circular edge — hole pitch is the single most common measurement taken on a plate, and Fusion defaults two circular edges to centre-to-centre. Edge labels are also identity-free (`"Edge 5, circle"`, no coordinates), so there is no way to tell which two holes were measured after the fact.

**CLOSED groom pass 30 (`dc49558`).** No wire change: every `OverlayEdge`
already carries its stage-1 signature (end_a, end_b, midpoint), so the centre
is derived client-side exactly as the kernel's own resolver does it
(`geometry.kernel.edges._circle_centre`). A picked circle's hero reading is
now "Centre to centre" (or "Centre to point"/"Point to centre" against a
vertex), with the kernel's minimum-distance reading kept at the row's end,
labelled "Min distance"; point-point measurements are unchanged ("Distance").
From/To lines now name each target with its centre coordinates. Verified
against the geometry service at full precision on the audit's own plate:
centres (-12,-3.5,6)/(12,3.5,6), centre-to-centre 25.0mm (0 error), kernel
minimum 17.0mm (0 error). New `measure-pitch.spec.ts` (real mouse picks) was
red before the fix; three independent mutations (centre off by /2.0001, min
label reverted, centre dropped from the label) each redden it. A
circle-picked-with-a-straight-edge case still gets no centre reading —
refiled as MEASURE-CIRCLE-STRAIGHT-EDGE-1.

<a id="item-edge-resolve-warn-1"></a>

### EDGE-RESOLVE-WARN-1

*kind: item-story*

kind: defect (trust/observability, backend + frontend). `docs/design/ topological-naming.md` §7.3 has always been explicit that stage-1 matching (which adjacency tier 3, `bf05482`, is one more tier of) is **best-effort and can silently mis-resolve** — a lone wrong match after a move is a documented, accepted residual, not a bug. Nothing in the product today tells the modeler when this happened: a feature that rebuilds via a best-effort tier reports exactly the same `OK` as one that resolved on an exact match, so a silently-wrong pick (the wrong edge, on a part with several similar ones) looks identical to a correct rebuild until someone notices the geometry is off. This is now sharper with tier 3 live: it "inherits the face matcher's best-effort §7.3 posture WHOLESALE, including its silent-retarget surface" (bf05482's own commit message).

<a id="item-instanceof-three-1"></a>

### INSTANCEOF-THREE-1

*kind: item-story*

kind: defect (test-infra hazard, not a live product bug). `three@0.185.1` ships dual ESM/CJS builds from one version, so `instanceof PerspectiveCamera` resolved through `require` is a DIFFERENT class object than one resolved through `import` — no version skew, no lockfile fix possible. MEASURED: exactly one `three` is installed and only `apps/web` depends on it, so the shipped Vite bundle has a single module graph and all 15 sites (12 in `Viewport.tsx`, plus `SketchScene.tsx`, `BenchBackdrop.tsx`, `glbGeometry.ts`) are CORRECT today — this is not a live defect. It bites in `vitest`, where `@react-three/fiber` resolves to its CJS dev build and pulls a second module record of `three`: probed against a real r3f root, `isPerspectiveCamera: true` while `instanceof PerspectiveCamera: false`. So the moment anyone writes a unit test for `Viewport.tsx`'s camera logic, all 13 of its sites will fail inexplicably, reading as a broken mock rather than a test- environment module-duality quirk.

<a id="closed-ready-craft12-outward-only-1"></a>

### CRAFT12-OUTWARD-ONLY-1

*kind: closed*

18. ~~**CRAFT12-OUTWARD-ONLY-1**~~ — **CLOSED (`202cc9d`, groom pass 27).** Root-caused: the bimodal pull was the preview re-fit ITSELF (not a second bounds-driven fit) — `frameOverrun` was a FIT ratio ("would a frame CENTRED ON THE ORBIT TARGET hold the subject") fed to a pose that deliberately parks the target OFF the subject (`targetShift`), so after a shrink the two disagreed and a second, spurious re-fit fired on the shrink itself. Fixed by projecting each corner exactly as the renderer will and returning distance from the FREE-RECT centre as a fraction of half-extent — `<=1` is on screen by construction, and a smaller subject cannot read larger, so "outward only" is now arithmetic, not a race. 10/10 held (was 6/11 pulled in 15.7x); unit: 5 of 22 cases redden against the old ratio. [src: `f8a1ecb`, groom pass 26; closed groom pass 27]

<a id="closed-ready-constraints-glyph-1280-1"></a>

### CONSTRAINTS-GLYPH-1280-1

*kind: closed*

19. ~~**CONSTRAINTS-GLYPH-1280-1**~~ — **CLOSED (`5444fa8`, same pass it was filed in).** Root cause: at 1280x800 a canvas click DRAWS while sketching (unlike the part workspace, where it orbits/selects), and `f9fcce6`'s Fit control sat on the bottom-centre seat the sketch rig's own -Y axis projects through at plane (0,-55) — `elementFromPoint` there resolved to `sketch-view-fit`, so the spec's centerline click became a Fit instead of a line start and the symmetric glyph never drew. Fixed by seating the sketch Fit bar off the LEFT edge of the reference cube's own box (same `*-view-cube` tokens, no new numbers), off both sketch axes. `constraints.spec.ts` 12/12 (was red at :1112), `sketch-fit.spec.ts` 3/3. Screenshots refreshed (`sketch-fit-{entry,after}-{1280,1440}.png`).

<a id="item-qa-cube-yield-settle-1"></a>

### QA-CUBE-YIELD-SETTLE-1

*kind: item-story*

kind: defect (test hardening). `qa-cross-wave-0913.spec.ts`'s "the cube is a control again once the pick is over" (now line ~592) clicks a cube facet, `await page. waitForTimeout(800)`, then compares `data-camera-pos` — the EXACT pattern `36360ae` (groom pass 27) fixed at this file's other cube-click case by polling `data-view` for the `direction` settle stamp instead of sleeping. Three agents have seen this case fail locally under load; CI has stayed green on it so far, which is consistent with the same load-sensitivity `36360ae` measured (7/7 red under load, 0/8 quiet) — triage before assuming either "load-sensitive timing gate" or "a real defect" without checking.

**CLOSED groom pass 29 (`d0604c5`+`856e3c0`):** both this ticket and the FB-7
CI flake (`founder-picking.spec.ts:555`) shared one root cause — a
sketch-exit fit reading the restore ease's in-flight CURRENT direction
instead of its committed destination, so the rest elevation after a sketch
was a function of frame timing (27-34 deg depending on load). `d0604c5`
moved FB-7's own case onto a camera-POSITION settle; `856e3c0` fixed the
shared mechanism (`committedAttitude`), landing the rest elevation at
23.11 deg, 0.00 deg off, across all 9 CPU x latency combinations tried —
closing both the FB-7 flake and this ticket's load-sensitive pattern.

<a id="item-gauge-readout-tag-1"></a>

### GAUGE-READOUT-TAG-1

*kind: item-story*

kind: cleanup (DRY, frontend). `9404cb1`'s `GaugeKeepOuts` finds a gauge's
value readout by string-matching the bare `<id>-readout` testid against
every `[data-gauge]` element's own id, because `GaugeTag` in
`ParametricGauge.tsx` carries a `data-testid` but no `data-gauge` of its
own — a comment in `useEdgeMarkAnchors.ts` names the collapse: "A
`data-gauge` tag on the readout ... would let this collapse to one rule."
Not a live defect (the current match is correct, per `9404cb1`'s own
measurement), just a second code path doing one job.

<a id="item-face-hover-bore-flake-1"></a>

### FACE-HOVER-BORE-FLAKE-1

*kind: item-story*

kind: defect (test hardening, unowned). `face-hover.spec.ts:463` ("the
addressed BORE wall, small laptop") is intermittent — found failing 2/6 while
verifying `9404cb1`, then reproduced at the same rate on source PREDATING
that commit, so PICK-PROXY-COLLIDE-1's pick-mark fix is not the cause. No
root cause identified yet; filed rather than silently retried.

<a id="item-perf-real-2b"></a>

### PERF-REAL-2B

*kind: item-story*

kind: defect (perf, kernel) — the residual PERF-REAL-2 left standing.
MEASURED (`09416c6`/`560eab1`): the checkpoint ladder cut edit #249 (near the
end of a 250-feature tree) from 34.1s to 1.85s (18.5x), but edit #3 (near the
START) is unchanged, 34.0-37.1s either way, matching a 36.1-37.1s cold
rebuild — every later feature must re-run regardless of any checkpoint, so
no cache scheme can buy this back. Needs a dependency-aware evaluator (only
features that reference the edited one's outputs re-run).

<a id="item-frontier-oversize-sideslot-1"></a>

### FRONTIER-OVERSIZE-SIDESLOT-1

*kind: item-story*

kind: question (perf trade-off, kernel). `83e3c67`'s one-entry exemption
holds a live checkpoint over the 128 MiB frontier budget ALONE — every other
lineage's frontier entry on that worker is evicted first, so its repeats
stay cache hits instead of full rebuilds. Deliberate and measured as the
right trade for a single worker, single large part (`/measure`,
`/tessellate`, `/export` all stay ~160ms hits instead of a full rebuild), but
under concurrent multi-user load on the same worker it means one big part
being worked can evict every other user's frontier entry repeatedly. Not
reproduced as a real-world problem yet.

<a id="item-pick-spec-reweigh-1"></a>

### PICK-SPEC-REWEIGH-1

*kind: item-story*

kind: capability (CI infra). `d3d0446`'s shard report measured pick-heavy
specs at ~1.3x their calibrated weight after `9404cb1`'s 3-frame seat-confirm
stamp landed (pick-affordance 382->642s, hole 309->419s, pick-mark-seat
212->336s) but re-entered only the specs `9404cb1` itself edited, not a full
re-measurement pass — the ratio held under load at manifest time, worth
confirming quiet.

<a id="item-ladder-provenance-weigh-1"></a>

### LADDER-PROVENANCE-WEIGH-1

*kind: item-story*

kind: measurement gap (kernel). `8077ede`'s checkpoint weight function
(`Detachable.weigh()`) includes every face `FaceProvenanceRecorder` keeps
alive via its history-lineage memo, alongside the state shapes and the
published/GLB bytes — all summed together. No measurement isolates what
share of a real checkpoint's weight the provenance memo alone contributes,
so it is unknown whether memo-trimming would be a worthwhile separate lever.

<a id="item-fillet-gauge-fps-floor-1"></a>

### FILLET-GAUGE-FPS-FLOOR-1

*kind: item-story*

kind: defect (test hardening, needs an owner). `fillet-chamfer-gauge.spec.ts`'s contract-β case asserts `frames.length` (sampled over `RELEASE_WINDOW_MS`) is `toBeGreaterThan(10)` — a message-based floor on how many animation frames rendered, not on the property the case actually cares about (rod and field agree every sampled frame). MEASURED: reproduces on the unmodified base tree too (`357b91e`'s own evidence: "fails on the UNCHANGED tree too (1 of 8, received 9)"; `f9fcce6`'s evidence: "reproduces on the CLEAN base 37e6e18 too, wandering between the fillet and chamfer cases").

<a id="item-pattern-scope-timeout-1"></a>

### PATTERN-SCOPE-TIMEOUT-1

*kind: item-story*

kind: defect (test hardening). "select Hole1, press Pattern, get six holes (not a six-times plate)" (line 324) and "a scoped pattern round-trips: re-opening it shows Hole1, not a guess" (line 530) both time out under CPU load without a code change implicated — same signature as this repo's documented quiet-window flake class (CLAUDE.md: "a real code regression fails identically every time; a contention flake wanders").

<a id="closed-ready-gate-floor"></a>

### GATE-FLOOR

*kind: closed*

1. ~~**GATE-FLOOR**~~ **DONE 2026-08-29** — both named gates floored, and the sweep of the other three found two more holes (`check-build-context`'s MAIN path, `check-tailwind-scale`'s accidental `max()` floor). Residue filed as GATE-FLOOR-2 (P3).

<a id="closed-ready-mateui-1"></a>

### MATEUI-1

*kind: closed*

2. ~~**MATEUI-1**~~ — **CLOSED 2026-08-29.** Rendering only: the diagnosis is already typed on the wire, so nothing in `services/geometry` changed. Mates now carry an `M1`/`M2` handle the message names and the panel shows; the "remove this one" action shipped in the same commit. See the entry below.

<a id="closed-ready-layout-1"></a>

### LAYOUT-1

*kind: closed*

3. ~~**LAYOUT-1**~~ — **CLOSED BY MEASUREMENT 2026-08-29, no fix needed.** Does not reproduce on HEAD (band and strip abut at 0.0 px; the audit measured 73 px). T-18 + the density pass had already fixed it. A clip-aware regression gate ships in its place.

<a id="closed-ready-ghost-1"></a>

### GHOST-1

*kind: closed*

4. ~~**GHOST-1**~~ — **CLOSED 2026-08-29.** A body with no stop of its own now ghosts while a sketch is open, as a derived default; a stop the modeler set is never overridden or silently restored. Filed CAMRESTORE-1 (P2) from the measurement.

<a id="item-stepname-1"></a>

### STEPNAME-1

*kind: item-story*

(kernel-architect, 2026-08-29) — the geometry writer already carries the instance name; the UUID is the fallback for a request that omits it, and the caller that omits it is `apps/web`.

<a id="closed-ready-hem-1b"></a>

### HEM-1B

*kind: closed*

7. ~~**HEM-1B**~~ — **CLOSED 2026-09-04.** The gated Save states its reason and an override toggle seeds its own field, so the audit's checked-and-empty dead end cannot be clicked into. The reported hydration bug did NOT reproduce at HEAD (measured: `k_factor: null` already loads unchecked). Filed **REASON-GATE-1 (P1)** from the survey it asked for: 15 of the 16 editor commit actions have the same silence, while 41 of 43 toolbar tools do not. ~~**REASON-GATE-1**~~ — **CLOSED 2026-09-04.** All seventeen say why, from one computation (`canSubmitX` is DEFINED as `blocker === null`), and all seventeen action rows moved into the pinned footer — a second unfinished rollout found in the same files, and the one that made the sentence legible at 1280x800.

<a id="closed-ready-mate-obs-2"></a>

### MATE-OBS-2

*kind: closed*

10. ~~**MATE-OBS-2**~~ — **CLOSED 2026-08-29.** `mateErrors` moved onto `AssemblySolve` (empty whenever stale) and the panel takes `solve`, not the raw evaluation, so there is nothing ungated left to read; the matrix gained it as an eighth case with a non-vacuity settled branch. See the entry below.

<a id="closed-ready-spec-10"></a>

### SPEC-10

*kind: closed*

**SPEC-10 and SNAP-5 are both SHIPPED (`42f6bbd`, `ecdf9ad`+`31ba716`) — see Done archive for evidence/gates.**

<a id="closed-ready-sketch-vocab-1"></a>

### SKETCH-VOCAB-1

*kind: closed*

**SKETCH-VOCAB-1 is fully SHIPPED (`38e37f5`, groom pass 15) — see Done archive for evidence/gates.**

<a id="closed-ready-mate-1"></a>

### MATE-1

*kind: closed*

**MATE-1 is CLOSED (`a2a6f9f`, gate `1ae3270`, groom pass 15) — see Done archive for evidence/gates. T-13 closes with it. T-14 (a different surface) does NOT — re-filed narrower below.**

<a id="closed-ready-measure-proxy-1"></a>

### MEASURE-PROXY-1

*kind: closed*

**MEASURE-PROXY-1 is CLOSED (2026-08-28, frontend-builder) — the occluder was drei `Html`'s own wrapper div, not a coincident face (Measure has no faces); 5 marks on a bare box -> 0 after `PickNode` opted back in, `viewport/PickMark.tsx`. See Done archive.**

<a id="item-name-2"></a>

### NAME-2

*kind: item-story*

kind: capability (observability, not correctness — the kernel resolver already returns the current signature + tier, per `c2700ee`'s own note: "a client can heal the reference — surfacing that on FeatureResult is a py-kit + web change, not a kernel one"). FIX: thread the resolver's tier through `FeatureResult` (py-kit schema + gateway pass-through) and render the existing `RE-ANCHORED` chip / anchorHeal affordance (`apps/web/src/drawing/anchorHeal.ts`'s pattern) on feature-tree rows whose tip subshape resolved on the tolerant tier, not just on drawing dimensions.

<a id="closed-ready-arc-degenerate-1"></a>

### ARC-DEGENERATE-1

*kind: closed*

- [x] (P2, S) **ARC-DEGENERATE-1 — SHIPPED (kernel-architect, 2026-08-29). 27 of 2000 payloads shipped an arc collapsed onto its own centre, and every gate agreed with all 27.** The asymmetry the ticket named was the only signal there was: a `SketchArc` derives its radius from three coordinates, so an annihilated one is a valid DTO whose residual is *zero* — a constraint satisfied by putting a point on a point is satisfied exactly. Population measured before choosing a fix, per the ticket: 25 `overconstrained`, 2 `underconstrained`, all at 4e-14 mm or less. Prior question re-asked (pin a reachable radius; re-solve from 8 pushed starts): **26 forced, 1 branch**; 16 of the 26 minimise to a single `coincident` between an arc's own centre and its own endpoint — literally the input shape `_add_entity` refuses, authored as a constraint. Fix is SOLVE-CRASH-1's with no new machinery (`_shippable_arc_points` -> the existing payload gate -> `sketch_conflicting`, constraint named); the input refusal keeps its exception but is now the same magnitude test rather than `== 0.0`. **The floor is NOT the circle's** — an arc's radius is a derived distance, not a solver parameter, and the fix's own effect on the settle moved trial 458 to 4.5e-9 mm, above `DEGENERATE_RADIUS_MM`; hence `DEGENERATE_ARC_RADIUS_MM = SATISFIED_TOL_MM`, re-measured after the fix. Census: annihilated arcs 27 -> 0, conflicting 287 -> 314, overconstrained 282 -> 257, solvable 1328 -> 1326, violated still 0. Three mutants, all restored. Gates: `just lint` exit 0, `uv run pyright` clean, geometry suite green. Filed as follow-ups: ARC-BRANCH-1, ARC-EXTRUDE-EPS-1. [src: SOLVE-CRASH-1 agent report, kernel-architect, 2026-08-29, filed by backlog-groomer pass 19]

<a id="closed-ready-arc-branch-1"></a>

### ARC-BRANCH-1

*kind: closed*

- [x] (P2, S) **ARC-BRANCH-1 — CLOSED (kernel-architect, 2026-09-04). A collapse the constraints do not FORCE is a bad starting guess, not a verdict, so the solver re-asks from a different one exactly once.** Trial 1906 now ships `r1 = 14.618, r2 = 29.236` at a worst residual of 3.6e-15 mm — the author's own `e1` untouched, and the branch ARC-DEGENERATE-1's live limit named; that test is DELETED here, as its docstring required. **The SETTLE-2 tension is real and resolves cleanly:** SETTLE-2 governs the settle's relationship to the plain solve it is HANDED, and the guard still runs unchanged over whatever baseline it gets; the restart runs one layer up and only where the plain solve produced NO shippable answer (geometry `read_back` substitutes and the payload gate refuses), so the choice is between an answer and no answer, never between two answers. **The start pose is the author's own sketch with only the collapsed entity relocated**, and the obvious alternative — restart from the whole solved answer — was built first and is worse: it inherits the first solve's unforced drag on `e1` and reverses the baseline SETTLE-2 judges against, so the settle's correct answer is discarded and it ships `r1 = 10.029`. General finding: **SETTLE-2's guard rests on the premise that the plain solve is a walk from the author's own values, and a restart seeded from a solved answer is the one thing that breaks it.** Not arc-only, and the generality found a second defect: of the **38** corpus solves that annihilate an entity, **36 are forced** and 2 are not — trial 1906 and trial **1593**, a CIRCLE in the same construction that SOLVE-CRASH-1 had counted as forced. Census: solvable 1326 -> **1328**, conflicting 314 -> **312**, underconstrained 1295 -> 1297; violated 0, reversed 0, annihilated 0/0, raised 0, and no other trial's payload moved by a bit. Determinism: two sweeps in one process, identical census and 2000 payloads bitwise identical. Mutants: disabling the restart reddens 3 of 5 new tests and restores the pre-fix census; the rejected pose reddens 2. Gates: `just lint` exit 0, `uv run pyright` clean, geometry suite green. [src: ARC-DEGENERATE-1, kernel-architect, 2026-08-29] TERRITORY: `services/geometry/src/geometry/sketch/planegcs_solver.py`, `services/geometry/tests/test_sketch_degenerate_arc.py`. agentType: kernel-architect.

<a id="item-arc-extrude-eps-1"></a>

### ARC-EXTRUDE-EPS-1

*kind: item-story*

kind: defect (tolerance). Found by ARC-DEGENERATE-1 (2026-08-29): `kernel/extrude.py` refuses an arc with `radius <= 0.0`, but the annihilated arcs measured in PBT-1's corpus include values of `1.6e-14` and `3.9e-14` mm, which clear that guard and become OCCT edges five orders under the 1e-7 m kernel tolerance. Exactly the seam SOLVE-CRASH-1 documented, one layer down. NOT fixed with ARC-DEGENERATE-1 for a reason worth keeping: `geometry.kernel` has NO dependency on `geometry.sketch` today, so importing `DEGENERATE_ARC_RADIUS_MM` there is a layering change, and writing `1e-9`/`1e-7` down a third time is the DRY violation the constant already documents itself against. P3 rather than P2 because ARC-DEGENERATE-1 closed both ends of the SOLVER, so nothing in the service can currently hand `extrude` such an arc — this is belt-and-braces against a future producer.

<a id="closed-ready-doctick-gate"></a>

### DOCTICK-GATE

*kind: closed*

**DOCTICK-GATE (`bd09f5b`, docstring fix `53e62b0`) and SPEC-9 (`e8702d5`) are both SHIPPED — see Done archive for evidence/gates.**

<a id="closed-ready-rect-1"></a>

### RECT-1

*kind: closed*

**RECT-1, SNAP-2, SNAP-3 and MIRROR-1 are all SHIPPED — see Done archive for full evidence/gates.** Their two live follow-ups stay in Ready:

<a id="item-snap-4"></a>

### SNAP-4

*kind: item-story*

kind: defect (interaction between two features that are each correct). Found 2026-08-16 while integrating SNAP-3, by a test that stopped passing for an informative reason rather than by inspection. Draw a line starting ON the origin: SNAP-3 correctly authors a coincident from the endpoint to the origin. Now press `x` (Fix) on that same endpoint — also correct in isolation — and the two constraints pin the same point twice, so the sketch reports OVER-CONSTRAINED. MEASURED: the `constraints.spec.ts` conflict-recovery case, which removes a bad dimension and expects `DOF 0 · CONVERGED`, instead reached `OVER-CONSTRAINED` and could not recover; it now draws clear of the origin to keep its own subject, which is a workaround in a test and not a fix in the product. WHY IT MATTERS beyond the tidiness: the report is TRUE — the point genuinely is over-determined — so the diagnosis is not lying, but the user authored only one of the two constraints and the other arrived silently from a snap. That is the "asks the user to delete something they did not knowingly create" shape that SKETCH-2's follow-up was filed for. OPTIONS, in preference order: (a) Fix on a point that already carries a coincident to the frame REPLACES it (the explicit verb supersedes the inferred one) and says so; (b) Fix is refused as "already grounded", matching the "Already horizontal." precedent RECT-1 relies on; (c) leave it and rely on the redundancy diagnosis — cheapest, and the one to argue against.

<a id="item-rect-2"></a>

### RECT-2

*kind: item-story*

kind: question (product decision, not a defect). Raised by RECT-1, which made it live: `PartPage.tsx`'s persist gate asks "has this sketch any constraints yet", and a drawn rectangle now answers yes immediately. RECT-1 deliberately preserved today's behaviour (bind only on a USER-authored constraint) so that a constraint fix did not silently change the save model, but the question is now worth answering on purpose. FOR auto-binding: Fusion and Onshape both autosave, and losing a drawn profile to a stray Escape is a real papercut. AGAINST: it creates a sketch feature for every exploratory rectangle, and it removes the "Discard N unsaved entities" confirm that the FB-13 flow work put there. Whichever way it goes it must apply to LINES and CIRCLES too — the inconsistency is the only outcome that is definitely wrong.

<a id="closed-ready-fb-21"></a>

### FB-21

*kind: closed*

**FB-21/FB-9 SHIPPED — see Done archive.**

<a id="closed-ready-export-1"></a>

### EXPORT-1

*kind: closed*

**EXPORT-1, REGISTER-1, REGISTER-2, VIEWCUBE-1, DXF-2a, DXF-2b, DXF-3, EXPORT-2, VISION-FIX-1 are all SHIPPED — see Done archive** (`3a7c4ca`, `044f1f7`, `e024daa`, `c28fbbc`, `a915bf1`, `5bfb528`, `fe72e4d`, `1880db2`, vision-steward `6dfb597`). Fresh Ready items from the same 2026-08-21 rotational-part audit that produced SOLVE-1/PICK-2 above:

<a id="closed-ready-export-3"></a>

### EXPORT-3

*kind: closed*

**EXPORT-3 is CLOSED (2026-08-28, frontend-builder) — one failed downstream feature no longer takes the good body's export with it. The gate was entirely client-side (the gateway already served the healthy prefix, byte-identical); `exportGate` now separates CAUSE from PARTIAL and the truth rides three surfaces (cell, notice, `-partial` filename). Mutation-tested both directions. See Done archive.**

<a id="closed-ready-revolve-1"></a>

### REVOLVE-1

*kind: closed*

**REVOLVE-1 is fully SHIPPED (`1b28dd5`, groom pass 15) — closes the last ABSENT-tier literal in the gateway contract. See Done archive for evidence/gates.**

<a id="closed-ready-pickmark-occlude-1"></a>

### PICKMARK-OCCLUDE-1

*kind: closed*

- [x] (P1, S) **PICKMARK-OCCLUDE-1 — CLOSED 2026-08-28. A pick diamond now sits at a point of its edge the BAND answers with, or it is not drawn there.** The agreement census rose 8/21 -> 11/21, and every mark that is DRAWN agrees (11/11); the ten that answer nowhere are `buried` — `opacity-0`, `pointer-events:none`, still tab-reachable and named, focus restores them. Perf measured, not asserted: 0.259-0.270 ms per band+surface hit-test, so the recompute is capped at 24 tests/frame (~6.5 ms) with a rotating cursor; a 40-step orbit costs +17% blocking over the same orbit with no marks. Three wrong turns and the evidence: ROADMAP + Done archive. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-8]

<a id="closed-ready-sel-8"></a>

### SEL-8

*kind: closed*

- [x] (P1, S) **SEL-8 — CLOSED 2026-08-28. Armed edge picks (Fillet's `PICK EDGES` mode) had no hover highlight on the real edge.** The ticket's three candidate causes were all wrong; the hit-test was fine and the DRAW was discarded by the depth test. Evidence, the mutation run and the design argument for keeping the marks: Done archive. The mid-face-marks half is NOT closed — see PICKMARK-OCCLUDE-1 above. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21" R-8]

<a id="closed-ready-a11y-toolbtn-1"></a>

### A11Y-TOOLBTN-1

*kind: closed*

**A11Y-TOOLBTN-1 is CLOSED (2026-08-28, frontend-builder) — `ToolButton` now wires `aria-describedby` to its caption in EVERY state, not only while disabled, so an enabled-but-qualified control (e.g. a partial export) reaches a screen reader instead of announcing nothing. Blast radius measured across 44 call sites via Chrome's own accessibility tree; `ExportToolGroup`'s name-folding workaround unwound in the same commit. See Done archive.**

<a id="closed-ready-reach-2-import-1"></a>

### REACH-2-IMPORT-1

*kind: closed*

**REACH-2-IMPORT-1 is CLOSED (2026-08-28, frontend-builder) — the STEP-import empty-state slot now sits adjacent to the copy that names it (422px -> 51px gap at 1280, no growth with screen size) and a new `ProgressTrack` primitive gives long imports a real indeterminate progress bar + Cancel. See Done archive.**

<a id="closed-ready-force-click-audit-1"></a>

### FORCE-CLICK-AUDIT-1

*kind: closed*

**FORCE-CLICK-AUDIT-1 is CLOSED (`6911352`, groom pass 16) — 22 call sites audited: 18 cargo removed, 3 legitimate refusals proven via a new `clickRefusedControl` helper, 1 vacuous test fixed. `force: true` now appears exactly once in `apps/web/e2e/`. See Done archive.**

<a id="closed-ready-pgtest-gate"></a>

### PGTEST-GATE

*kind: closed*

**PGTEST-GATE is CLOSED (`ef5d1c5`, 2026-08-28, platform-builder) — a missing PostgreSQL now fails loudly instead of silently skipping 37% of the documents suite. Pass-8's self-correction to Pass-7 M4 (CI's ubuntu-latest image already shipped PG 16.15 at the searched path, so the 172 tests were almost certainly already running) is CONFIRMED from source (`actions/runner-images` fetched directly), not inherited — see `docs/AUDIT-ENGINEERING.md` M4/N8 and the correction note there, still accurate, no further action needed. Negative control exit 0 -> 1; whole-repo suite unaffected (4090 passed). See Done archive. PGTEST-GATE-VACUOUS-NONGOAL (P3, below) records one deliberately unfloored case.**

<a id="closed-ready-gate-floor-2"></a>

### GATE-FLOOR

*kind: closed*

- [x] (P1, XS) **GATE-FLOOR — DONE 2026-08-29 (platform-builder). The two named gates were vacuous exactly as audited the fourth time, and checking the other three found TWO MORE holes.** Fixed: the named pair now carry `EXPECTED_CHECKS` (8 and 23). NEW, and the reason the "check the others" instruction earned its keep — (a) `check-build-context.py`'s **main** path (the one CI runs, standing in for the `docker build` the 403-blocked registry makes unreachable here) printed "0 COPY source(s) reach the build context" and exited **0** when a Dockerfile parsed but yielded no COPY; now floored at `MIN_COPY_SOURCES = 8` against a real 15, plus two self-test cases. The audit table's "n/a (straight-line, not list-driven)" was true of its SELF-TEST and blind to its main path — it matched the `all([])` idiom instead of asking the question the idiom stands for. (b) `check-tailwind-scale.py` was never in the table; same `failed = 0` shape, exiting 1 only because `max()` raises on an empty sequence — an accidental floor one `default=0` from a silent pass. EVIDENCE: identical probe, committed HEAD vs fix — HEAD "self-test passed" / "passed - 0 cases" exit 0; fix "SELF-TEST RAN 0 of 8 / 0 of 23 checks" exit 1; `check-build-context` zero-COPY case 0 -> 1; sweep of all seven self-test gates with the list emptied at the START of the verdict block = 7/7 exit 1 (was 2 vacuous + 1 `ValueError`). Real inputs unchanged and green; `just lint` exit 0. Sound on inspection, no change needed: `check-doc-tick`, `stage-doc-hunks`, `e2e-shard-audit`, `e2e-shard-plan`, `check-licences`, `check-compose`. `check-ui-parity.py` has the same main-path vacuity but gates nothing (in neither `just lint` nor CI) — filed as GATE-FLOOR-2 below. Original entry follows. kind: defect. MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 7" M7, reproduced not inferred): `check-workflow-concurrency.py:481` and `check-mutation-markers.py: 1115` both use `if all(ok for ok, _ in results)` with no count floor; injecting an empty check list into each makes `--self-test` print "self-test passed — the gate can fail" / exit 0. `e2e-shard-audit.py: 309` and `stage-doc-hunks.py:544` already carry the fix (an `EXPECTED_CHECKS` constant + `if len(results) < EXPECTED_CHECKS: return 1`). FIX: copy that four-line pattern into the two gates named above. ACCEPTANCE: the same empty-list injection that currently prints "the gate can fail" now correctly fails; `just lint` stays green on the real gates. [src: docs/AUDIT-ENGINEERING.md "Pass 7" M7, filed by backlog-groomer pass 8] **Bumped P2→P1: reproduced UNCHANGED a second time** (`docs/AUDIT-ENGINEERING.md` "Pass 8" N3): `check-mutation-markers.py`'s own self-test message literally prints `"self-test passed - 0 cases"` and returns 0 — it has `len(results)` in hand, interpolates it into the success string, and never compares it to anything. Two consecutive passes recommending an already-written four-line fix with zero action is a process signal on its own, independent of the gate's own severity. **REPRODUCED UNCHANGED A THIRD TIME, groom pass 11 (2026-08-24, engineering Pass 9 N8a):** re-ran with `tail`-swallowed exit-code measurement corrected (a methodological note worth keeping: piping `--self-test` through `tail` reports `tail`'s exit code, not the gate's, and would print 0 for a gate that correctly exited 1) — both gates still print their own vacuity and exit 0. Three passes, zero action, four-line fix each: this is now the board's clearest example of the "gate hygiene items don't get built" pattern the same audit names in N10. TERRITORY: `scripts/check-workflow-concurrency.py`, `scripts/check-mutation-markers.py`. agentType: platform-builder.

<a id="item-gate-floor-2"></a>

### GATE-FLOOR-2

*kind: item-story*

kind: defect, filed by platform-builder 2026-08-29 from the GATE-FLOOR sweep. (a) `check-ui-parity.py` has the same main-path hole `check-build-context` had: `rows = classify(...)` then `gaps = [... != AUTHORABLE]`, so a spec that fails to load or an empty corpus yields no rows, no gaps, no orphans and exit 0 — and its numbers are quoted in `docs/ROADMAP.md`'s Current focus (84/85 operations, 97/109 literals), i.e. already trusted as a measurement while being unfloored.

<a id="item-dep-audit"></a>

### DEP-AUDIT

*kind: item-story*

kind: capability. MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 7" M8): no `.github/dependabot.yml`, no `pnpm audit`/`pip-audit` step in CI, no CodeQL, no container scan — the licence gate (`check-licences.py`) answers a different question entirely (what a dependency is licensed as, not whether it's vulnerable). All 18 current findings are in `devDependencies` (eslint/openapi-typescript/ postcss/jsdom chains), none reach the shipped SPA bundle or a service image today — P2, not P1, because of that path check, but two (`js-yaml` inside `just gen`, `postcss`/`nanoid` at build time) are a supply-chain path even so. FIX: `.github/dependabot.yml` (npm + pip + github-actions ecosystems, weekly); a non-blocking `pnpm audit --audit-level=high` step in `ci.yml`; `pip-audit` against `uv.lock` for the Python half (no `uv audit` subcommand exists).

<a id="item-spec-8"></a>

### SPEC-8

*kind: item-story*

kind: defect (test, on a geometric-correctness claim). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 8" N5, uncommitted, recovered and preserved by backlog-groomer pass 9): `:267` `if ((await picker.count()) === 0) return;` skips the rest of the test — including the mixed-material combined-mass assertion (`84.56`) — if `material-default-select` isn't found. The comment's premise expired: `MaterialSection.tsx:124` ships that testid today, so the guard is now pure risk (a future regression removing/renaming the picker reports PASS instead of catching it). Same shape at `:249`. FIX: `await expect(picker).toHaveCount(1)` in place of the early return at both sites.

<a id="item-auditor-ports-1"></a>

### AUDITOR-PORTS-1

*kind: item-story*

kind: capability (process). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 8" recommendation #8): the engineering audit found the product auditor's stack live on the shared ports mid-pass and had to boot an isolated stack (the documented CLAUDE.md recipe, ~1 hour) to run any browser suite at all — second consecutive pass this has cost real time. FIX: the product-auditor agent brief defaults to an isolated port profile (it runs the longer, heavier browser session), leaving the shared ports free for the lighter/quicker engineering-audit checks.

<a id="closed-ready-qa-r1"></a>

### QA-R1

*kind: closed*

**QA-R1 is CLOSED (`5957252`, groom pass 15) — fixed the primitive (`Flyout` label collapse), not the instance. See Done archive.**

<a id="closed-ready-qa-r2"></a>

### QA-R2

*kind: closed*

**QA-R2 is CLOSED (`0cee656`, e2e barrier hardened `d2b1d26`, groom pass 15) — the angle glyph now reads `SolvedSketch.angles`. See Done archive.**

<a id="closed-ready-reach-3-flow"></a>

### REACH-3-FLOW

*kind: closed*

**REACH-3-FLOW is CLOSED (2026-08-28, frontend-builder) — Sheet 1 is now born from the orientation proposal (a 40x40x150 column lands A4 portrait at 1:2, was landscape at 1:5), via one `sheetHeaderForNewSheet()` derivation shared by all four create paths. The orientation-flip half's promised re-fit was IMPOSSIBLE server-side (documents refuses a per-view re-scale, H2), so the trade moved to the set-up screen instead of shipping a broken promise. See Done archive. Residual: **SHEET-RESCALE-1** below.**

<a id="item-sheet-rescale-1"></a>

### SHEET-RESCALE-1

*kind: item-story*

kind: capability gap (not a regression — no client ever could). MEASURED 2026-08-28 while closing REACH-3-FLOW, against the real stack: `PATCH /views/{id}` with a new `scale` returns 422 `sheet_view_scale_mismatch` on any multi-view sheet (documents' H2 "one sheet, one source, one scale" guard), and the refusal cannot be sequenced around — the guard compares against `siblings[0]`, which still holds the OLD scale whichever view you write first. There is no sheet-level re-scale verb, and post-layout the web Scale control is a read-only `Readout`, so the scale a sheet was laid out at is permanent. Consequences the user feels: flipping paper orientation cannot re-fit (REACH-3-FLOW closed this by making the cell honest instead), and a part that grows after drafting can only be re-scaled by deleting the sheet. FIX: a sheet-level re-scale on `PATCH /sheets/{sheet_id}` that rewrites every view's scale in ONE transaction (the H2 invariant then holds throughout — it is per-view writes that cannot satisfy it), plus the web Scale picker staying live post-layout.

<a id="item-titleblock-stamp-1"></a>

### TITLEBLOCK-STAMP-1

*kind: item-story*

kind: capability (deliberate, documented deviation — not a defect in what shipped). `5438b73`'s own commit message: the plan put the convention cell in the sheet's TITLE BLOCK (a drafter's actual reading location, and the right long-term home) but `ComposedTitleBlock` is composed SERVER-side, so a DOM-only cone symbol there would be worse than absent — present on screen, gone from every exported SVG/PDF/DXF. The cell was placed in the sheet header instead, correctly, as an interim step. FIX: stamp the ISO cone symbol (mirrored by `right_sx`'s sign, per the header cell's own derivation) into the geometry service's composed title block so it reaches every export format, not just the screen.

<a id="closed-ready-asmdraw-fit-1"></a>

### ASMDRAW-FIT-1

*kind: closed*

**ASMDRAW-FIT-1a is CLOSED (`79ca41c`) — `GET /assemblies/{id}/extents` returns the mate-solved compound's AABB, asserted on the geometry (a fixture where solved and seeded differ), never the status code. See Done archive.**

<a id="closed-ready-asmdraw-fit-1-2"></a>

### ASMDRAW-FIT-1

*kind: closed*

**ASMDRAW-FIT-1b is CLOSED (`69b3ef7`) — the assembly drawing sheet fit-scales off those solved extents (1:1 -> 1:2 on the founder's rig; title-block overlap gone, all four frames measure 0 px² overlap). See Done archive.**

<a id="closed-ready-extrude-coarse-step-1"></a>

### EXTRUDE-COARSE-STEP-1

*kind: closed*

**EXTRUDE-COARSE-STEP-1 is CLOSED (`1661a5b`) — two independent defects, both fixed: the coarse step now lands on the next multiple of the step in the direction pressed (12.4713 -> Shift+Up -> 15, not 15.5/16), and a queued-ack race that silently dropped fast keyboard presses is gone. See Done archive. Note: `nudgePlacement` (drawing authoring) still uses the older round-then-add variant this fix deliberately did not touch — see NUDGE-PLACEMENT-QUANTISE-1 below.**

<a id="item-nudge-placement-quantise-1"></a>

### NUDGE-PLACEMENT-QUANTISE-1

*kind: item-story*

kind: defect. From 12.4713 a coarse press gives 13, silently skipping 12.5 — the same shape EXTRUDE-COARSE-STEP-1 (`1661a5b`) fixed on the extrude drag handle by taking "the next multiple of the step in the direction pressed" instead of round-then-add. That commit deliberately did NOT extract a shared helper: the two nudges share three lines of arithmetic and nothing else (`nudgePlacement` moves a 2-D seat on a sketch-authoring state machine in sheet mm; `nudgeDepth` moves a 1-D depth clamped to a submittable range with its own key map), so a shared primitive would move code out of both files without removing any duplicated LOGIC — the premature abstraction DRY excludes. What they must share is the RULE, and `1661a5b` states it in both files and points each at the other; this item brings `nudgePlacement`'s BEHAVIOUR into line with the rule it already cites, without merging the two functions. FIX: change `nudgePlacement`'s quantisation from `round(v/step)*step` (or equivalent round-then-add) to the next multiple of the step in the direction of the press, matching `steppedDepth`'s rule.

<a id="item-checkuiparity-fp-1"></a>

### CHECKUIPARITY-FP-1

*kind: item-story*

kind: defect (tooling — the scan's own docstring already admits residual error in both directions; this is a concrete instance, and it lands in the direction that matters, since it hides a literal that IS reachable and blesses one that is not). Cause: `_reachable_in`'s bare-substring match — the string `"open"` appears inside unrelated identifiers in the web corpus (e.g. words containing "open" as a substring), producing a false AUTHORABLE hit for a literal the UI may not actually author, while the exact match for `"closed"` the hem form actually sends is not found by the same loose logic. FIX: match hem-type literals as whole tokens/string values (e.g. a quoted-string or property-value boundary), not bare substrings.

<a id="item-e2e-shard-count-1"></a>

### E2E-SHARD-COUNT-1

*kind: item-story*

kind: capability (CI infra). `7c9ff95` (groom pass 27) fixed the shard-4 timeout by re-measuring the duration manifest, but the resulting spread's headroom is 1.3x — down from a documented 2.1x a month ago, as the suite grew 145→180 spec files — and `.github/workflows/e2e.yml`'s own header states "by the rule above that is the point to weigh N=5 or 6" once T/N approaches the cap.

**CLOSED groom pass 29 (`d3d0446`).** Matrix raised 4->6; re-entered
`pick-proxy-collision` (new) plus 16 specs edited since the last manifest
(`9404cb1`'s 3-frame seat-confirm made pick-heavy specs ~1.3x costlier —
excluded from the calibration ruler so they cannot bend the ratio they are
divided by). Predicted 22.6 CI-min/shard at N=6 (1.77x headroom), checked
against the d0604c5 CI run at rms 2.4 (was rms 5.9 on the stale manifest).
`e2e-shard-audit.py` gained `--expect-shards`/`--workflow` cross-checks.
Confirmed on a real run: `55df4d3` read `d3d0446`'s `e2e` at 8 total jobs
(6 shards + complete + dist-bundle), 0 failed.

<a id="item-viewbar-dry-1"></a>

### VIEWBAR-DRY-1

*kind: item-story*

kind: defect (DRY, frontend). `f9fcce6`'s `SketchViewBar` (in `Viewport.tsx`) and `ViewBar`'s own container (`components/ViewBar.tsx`) both render `role="toolbar"`, `data-viewport-chrome="view-bar"`, and the identical shell classes (`flex items-stretch border border-hairline bg-anvil shadow-float`) — the exact "fix the primitive, never the instance" case CLAUDE.md's design mandate names. **RE-VERIFIED after `5444fa8` moved the sketch bar to hang off the reference cube:** the duplication survives the move — only the POSITIONING classes now differ (`SketchViewBar` anchors to the cube's own seat box via `right-full top-1/2 mr-2 -translate-y-1/2`, `ViewBar` docks at `bottom-3 left-1/2 -translate-x-1/2`), the shell styling is still copy-pasted.

<a id="item-sketch-fit-grid-occlude-1"></a>

### SKETCH-FIT-GRID-OCCLUDE-1

*kind: item-story*

kind: defect (frontend, UNVERIFIED dimensions). Reported at ~608x65px at the top-left of the sketcher canvas; see `docs/screenshots/sketch-fit-after-1280.png`. A pixel scan of that specific PNG did not find a flat/uniform block of those exact dimensions at that position (the feature-tree panel there measures ~332x236 and IS a legitimate DOM panel, not a canvas artifact) — so either the dimensions/position have drifted, the report was against a different viewport state, or this is a rendering difference not visible in a static screenshot diff.

<a id="closed-next-solve-crash-1"></a>

### SOLVE-CRASH-1

*kind: closed*

**SOLVE-CRASH-1 is CLOSED (2026-08-29, kernel-architect, arbitrated P2->P1) — the untyped 500 is gone. The twelve crashes were TWO defects wanting opposite answers, measured before a fix was chosen: 3 had a negative radius of real magnitude (a planegcs branch convention, not degeneracy) and now solve normally at 1.8e-13 mm worst residual; the other 9 are genuinely annihilated (`r=0` the unique solution) and now return `sketch_conflicting` via the existing payload gate rather than crashing. No new machinery, no contract change. Census: raised 12 -> 0, solvable 1327 -> 1328, conflicting 276 -> 287. See Done archive / `docs/CHANGELOG.md` for the full two-defects-one-crash argument.**

<a id="item-perf-real-3"></a>

### PERF-REAL-3

*kind: item-story*

kind: defect (perf, delivery). MEASURED on `rc-buggy-suspension` (211 solids, 6 867 576 triangles): 142MB GLB, 90MB gzipped. `docs/PERF.md`'s 5.2x-11.8x compression figures were measured on toy parts, where the win was JSON overhead; a real mesh is dominated by incompressible vertex data, and 142MB is not deliverable to a browser on any connection a user has. Ranked #3 in `docs/GEOMETRY-QA.md`'s gauntlet ranking.

**STILL OPEN, unrelated to the item below** — see BACKLOG.md's Next (P2)
for the live ticket.

<a id="item-perf-real-3-cache-key"></a>

### PERF-REAL-3 (reused id — overlay cache-key collision)

*kind: closed*

**A DIFFERENT defect than the mesh-payload PERF-REAL-3 above; three landing
commits reused this id for it, so it is recorded here rather than minted a
fresh one.** kind: defect (perf, kernel). Root cause of a 15.3s
`/geometry/overlay` on the imported `gearbox-11752`: the overlay evaluated
with `record_history=True`, and `record_history` was IN the rebuild-cache
key, so a face pick after every open or edit was a guaranteed miss on a
lineage of its own and re-ran the whole tree — publish work (tessellation,
mass properties, validity) included, none of which the overlay reads.

**CLOSED groom pass 30 (`496d275`+`989349c`+`9c21801`).** Every evaluation
now records per-face provenance fingerprints and the flag is gone from the
key (`CACHE_KEY_VERSION` 3), so `/evaluate`, `/overlay`, `/measure`,
`/tessellate`, export and drawings share ONE lineage. Measured on
`gearbox-11752` (1,018 faces): overlay after evaluate 7,861ms MISS ->
2,222ms HIT in process (~8.8s -> ~2.1s via the gateway); cold open 8.5s (STEP
parse 24%). `989349c` cut the resulting cold-rebuild recording cost from
~6-8% to 0.06-1.6% (403ms->4ms on gearbox, 1,477ms->390ms at N=200) by
resolving snapshot faces to a distinct-face index instead of re-fingerprinting
copies on every ladder-rung fork. `9c21801` corrected the "separate cache
lineages, warmed in priority order" language in `loft-wire`'s `WarmLineage`
docs and `gateway/affinity.py` to match (comments/contract description only,
no behaviour change) — five more stale "lineages" references elsewhere were
found and refiled as LINEAGES-DOCSTRING-STALE-1. New
`test_overlay_after_evaluate.py` asserts cache counters (+1 hit, +0 misses)
and was red before the fix; disabling recording reddens 8 gates. Geometry
suite 3,191 passed / 1 skipped throughout. A cache-hit overlay still costs
~2.1s (extraction ~1.3s + a publish-time validity re-check ~0.5s kept
deliberately for CM-6b) — refiled as OVERLAY-CACHE-HIT-RESIDUAL-1; a
persistent content-addressed STEP import cache (saves ~2s once per part on a
cold/different worker) refiled as STEP-IMPORT-CACHE-1.

<a id="item-nurbs-fixture-1"></a>

### NURBS-FIXTURE-1

*kind: item-story*

kind: question (blocked on acquisition). The `mesh_glb_id` non-determinism F2 fixed this pass reproduced ONLY on foreign imports at 1018+/4123 faces (gearbox-11752, kuka-kr600); twelve of our OWN goldens exported to STEP and re-imported are all byte-idempotent (0 differing bytes), so the fix has no regression fixture that can catch a re-introduction of the bug. `just gauntlet`'s five fixtures are fetched by URL+sha256 and explicitly NOT redistributable (no LICENSE in the hosting repo).

<a id="item-step-roundtrip-coverage-1"></a>

### STEP-ROUNDTRIP-COVERAGE-1

*kind: item-story*

kind: defect (golden coverage gap). MEASURED: `rc-buggy-suspension` (211 solids, 26 306 edges) round-trips through STEP export/re-import gaining 22 edges, with faces/solids/shells all identical; the KUKA's converged round-trip volume delta is 5.3e-6, stable across tolerances — 53x the golden suite's `ROUNDTRIP_TOL=1e-7`. No existing golden has 10 000+ edges or 200+ solids, so this scale is structurally unreachable by the corpus today.

<a id="item-gauge-quiesce-1"></a>

### GAUGE-QUIESCE-1

*kind: item-story*

kind: defect (test hardening, not a product defect). MEASURED by the CRAFT-13 fix (`b4e7821`): the post-release settle tail the window races is 1.09-1.12s on the base tree and 0.78-0.80s with the fix applied — the fix makes it SHORTER, not the window safer, and both readings sit close enough to 1200ms that CI contention can plausibly cross it (two cases, `:251` contract-β and `:333` arrow keys, already fail in batch and pass in isolation on both trees).

<a id="item-scorefresh-pending-1"></a>

### SCOREFRESH-PENDING-1

*kind: item-story*

kind: defect (gate completeness, self-referential). `scripts/check-scorecard-freshness.py` exempts any row whose cell contains the word `PENDING` from its git staleness check, with no age bound, expiry, or cap on how many rows may be PENDING at once — and the self-test asserts this is intentional ("marking most rows PENDING does NOT trip the vacuity floor"). Live example the day it shipped: 5 of 13 rows read PENDING, including the two rows that day's two biggest commits were evidence for. A row marked `PENDING — awaiting the gauntlet` in September could still say PENDING in March with September's prose beside it, and the gate would report green every day.

<a id="item-required-query-1"></a>

### REQUIRED-QUERY-1

*kind: item-story*

kind: defect (structural, gate gap — SCRIPT-1 follow-up, related to the `delete_feature` P0 this pass fixed one instance of). Ten operations declare a required query param (`expected_version`, `expected_tree_version`, `kind`, `format`); until `_send` enforces it, the scripting API's "no undeclared call" guarantee covers bodies and paths only, and every future verb added to the library can reproduce the same 422-on-every-call defect for free. Related and unenforced in the same place: an UNDECLARED query key is silently ignored by FastAPI's `extra="ignore"` default.

<a id="item-perf-asm-1"></a>

### PERF-ASM-1

*kind: item-story*

kind: capability (measurement first). `docs/design/DIRECTION-ASSEMBLIES.md` §7: no assembly in this repo has ever been solved/rendered past 2 instances; build a fixture (1 unique bracket + 1 unique plate + N identical fastener instances, N=10/30/100) and measure, separately: evaluate+ resolve+solve+tessellate wall clock; time-to-first-frame; orbit/zoom frame rate with the assembly loaded; time to author+solve one more mate once the scene is populated. Record as a golden + CI budget (same shape as existing part-evaluation perf gates, RESEARCH §9). ONLY IF a number is bad, propose the smallest fix ranked by likelihood: (1) viewport draw-call/material count if render/orbit is the bottleneck (`apps/web/src/viewport/**`-only); (2) moving assembly evaluation onto the arq queue if solve wall-clock blocks the request thread (a RESEARCH §4/§10 update in the same commit as the code). Do NOT build either fix speculatively ahead of the number.

<a id="item-pick-asm-1"></a>

### PICK-ASM-1

*kind: item-story*

kind: verification-first (the fix may already be sufficient). Build a 3-4 instance scene where at least two DIFFERENT faces on DIFFERENT instances project to overlapping screen regions from a default camera angle — the realistic case, not the original defect's clean arrangement — and confirm the existing `mateDepthStack` cycling reaches every plausible face. If it does not, the fix is scoped to `apps/web/src/viewport/mateDepthStack.ts` and its consumers, following MATE-1's own pattern.

<a id="item-bom-asm-1"></a>

### BOM-ASM-1

*kind: item-story*

**REPLACES the prior "Assemblies — RECURSIVE / indented BOM" entry** (same scope, pulled forward per `docs/design/DIRECTION-ASSEMBLIES.md` §7, which closes a real gap in the ➖ Assemblies scorecard row rather than deferring behind Phase 5). Walk the (already-acyclic) sub-assembly instance graph; roll a part appearing N× inside a sub-assembly instanced M× up to N·M; carry a `level`/`parent_key` so the client can render an indented tree. The flat aggregation, `BomLine` DTO, and acyclicity guarantee already exist — this is an additive walk over them, not a new mechanism.

<a id="item-flow-asm-1"></a>

### FLOW-ASM-1

*kind: item-story*

kind: capability (flow, scope-bounded deliberately). Does NOT add a new persisted reference type: when a newly-inserted (or newly-selected) instance has exactly one planar face or circular edge geometrically compatible (coincident- or concentric-candidate, within tolerance) with exactly one face/edge on an already-placed nearby instance, surface a one-click "Mate these" suggestion using the EXISTING `coincident`/`concentric` mate-create endpoint — no schema change, purely a suggestion computed and discarded client-side (or a thin geometry-side candidate-pairs query, an implementation choice for the builder). If more than one candidate is plausible, show the ambiguity as a short pick list — never guess.

<a id="closed-next-camrestore-1"></a>

### CAMRESTORE-1

*kind: closed*

- [x] (P2, S) **CAMRESTORE-1 CLOSED (2026-09-04, frontend-builder) — leaving a sketch gives the VIEW back, not just the camera.** The sketcher remembers the pose it takes and requests it back through the same view-command seam the rail and the reference cube use (a new `restore` kind carrying a `ViewPose`), so the part rig performs it — one rig on the camera, an ease, `prefers-reduced-motion` honoured. Measured with the direction read off the live camera, not a brightness census (that census is exactly what this defect broke): pre-fix the exit view was **78.05 deg** off the pre-entry view (and read (0,-1,0) — straight down, the ticket's flat diamond), **90.00 deg** from a named FRONT, and **78.04 deg** across the ticket's own draw-and-save flow; post-fix all three are **<= 1 deg**. A deliberate mid-sketch orbit is NOT overruled — the remembered pose is a default an explicit action beats, the `905fcc4` rule — and mid-ease gestures do not count, because the ease overwrites them. Orthographic zoom is carried, so a parallel view returns at the same apparent size (5% band). 2 unit cases, 4 e2e cases, mutation-tested in both directions: no-restore reddens 3 of 4 and leaves the orbit case green; unconditional-restore reddens ONLY the orbit case (27.25 deg of overruled turn). Screenshots: `docs/screenshots/camrestore-sketch-exit-{before,after}-laptop.png`. Two specs needed the wait they had been getting by accident stated out loud: `part-visibility`'s ghost A/B (its second sketch entry now eases, where a stranded camera used to make the park a no-op) and, separately, `founder-picking`'s face-seat pick, which was RED at the tip for its own reason — see the entry below.

<a id="item-tipred-1"></a>

### TIPRED-1

*kind: item-story*

kind: defect (CI). Found while sweeping for CAMRESTORE-1 regressions and reproduced with `apps/web/src/viewport/**` reverted to the tip, so it is not that change: after `parkThenClick` on a drawn corner the selection readout never reaches "1 pt", i.e. the PICK does not land. 3 runs of 3, and still red at `4d359dd`. The pick path was changed by the SEL-2 commits (`f4273d3`, `4009042`, `replacementPick`), which is the first place to look.

<a id="item-solve-conflict-moved-1"></a>

### SOLVE-CONFLICT-MOVED-1

*kind: item-story*

kind: defect (contract). MEASURED by PBT-1's sweep: **2 of 2000**. `SolvedSketch.entities` documents "for conflicting/diverged sketches the input positions are returned unchanged", and `solve()` honours it for a diverged solve and for a payload the residual gate reclassifies — but when planegcs itself diagnoses a conflict on a solve that CONVERGED, the branch falls through to `read_back()`. So a client told "conflicting" is handed moved geometry, and the UI's revert-to-input assumption is wrong for those cases. FIX: either return the input on that branch (matching the doc) or change the doc; one line either way, but it is a contract decision.

<a id="item-solve-overconstrained-ambiguous-1"></a>

### SOLVE-OVERCONSTRAINED-AMBIGUOUS-1

*kind: item-story*

kind: defect (contract). MEASURED by PBT-1's sweep: of 282 overconstrained payloads, **17 returned the input** and 265 carried solved geometry. `_map_status` puts `redundant` ABOVE `not solved` in precedence, so a DIVERGED solve with a redundant constraint is reported as `overconstrained` — the divergence is masked, and the DTO's own hedge ("consistent overconstrained cases") is the only hint that the two exist. Consequence: no consumer can decide whether to adopt the returned coordinates, which is exactly the decision the sketch UI makes on every solve. FIX options: a separate status, or a boolean on the payload saying whether the entities were solved.

<a id="closed-next-hem-1c"></a>

### HEM-1C

*kind: closed*

**HEM-1C is CLOSED (2026-08-28, frontend-builder) — the hem card now derives every number it shows from the hem rule instead of a stale base-flange claim, and the override guidance states only values the evaluator accepts. New live `Gap` readout. Ratios live in one place, pinned against the py-kit source by a unit test. Mutation-tested three independent ways. See Done archive.**

<a id="closed-next-hem-1d"></a>

### HEM-1D

*kind: closed*

**HEM-1D is CLOSED (2026-08-28, frontend-builder) — a Closed/Open segment now authors the shape (`buildHemParams` sends the user's choice, was hardcoded `closed`); asserted on the BUILT BODY (open hem stands 6.0 mm vs closed's 4.2 mm), not a 2xx. Fixes the `check-ui-parity.py` false-positive direction CHECKUIPARITY-FP-1 (below) also names. See Done archive.**

<a id="closed-next-hem-1b"></a>

### HEM-1B

*kind: closed*

- [x] (P2, S) **HEM-1B — CLOSED (frontend-builder, 2026-09-04). The gated Save now says why, and "override checked with no value" is no longer a state a click can reach.** The reported HYDRATION bug did not reproduce at HEAD and the probe says why: the server stores `k_factor: null` for an inherited K, and `formFromHemParams` already reads that as unchecked — re-opening the orphaned hem gave `aria-checked="false"`, no K field, Save ENABLED. What DOES reproduce, in two clicks, is the audit's screenshot: ticking an override left the field blank, and blank is "pending" to every field validator, so Save went `aria-disabled="true"` with `title: null` and nothing on screen. Fixed at both ends — `hemSubmitBlocker` is now the single source of the gate AND its sentence (`canSubmitHem` is defined as "no blocker", cross-checked against `buildHemParams` over 66 form/pick/ anchor combinations), and ticking an override SEEDS the field from the value it replaces. The action row also moved into `EditorCard`'s pinned footer: at 1280x800 the reason's own centre hit-tested to `feature-tree-section`, i.e. the explanation had fallen out of the card. Survey filed as REASON-GATE-1 below (15 of 16 editor commit actions have the same silence). Mutation evidence, gates and the before/after shots: `docs/CHANGELOG.md`. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)" S-26, split from HEM-1 by backlog-groomer pass 16]

<a id="closed-next-reason-gate-1"></a>

### REASON-GATE-1

*kind: closed*

- [x] (P1, M) **REASON-GATE-1 — 15 of the 16 editor commit actions can go grey with no reason on screen, which is HEM-1B repeated once per verb.** kind: defect (generalised from HEM-1B's second half, measured 2026-09-04 while closing it). `PanelActionCell` has carried a `disabledReason` prop since UI-REVIEW 2026-07-30 — it takes the caption's line while gated and is wired as the button's `aria-describedby` — and only `hole-submit` and (now) `hem-submit` pass it. The other fifteen (`base-flange`, `chamfer`, `combine`, `corner-relief`, `datum`, `draft`, `edge-flange`, `extrude`, `fillet`, `loft`, `mirror`, `pattern`, `revolve`, `shell`, `sweep`) share the exact `canSubmitX(form, …) && !saving` -> `disabled={!canSubmit}` shape the hem had, so every "no pick / no body / empty override" state is a silent dead end there too. The TOOLBAR tier is fine by contrast and is the model to copy: 41 of 43 gated `ToolButton`s carry a gate-aware `caption` ("Add a base flange first"), the two exceptions being `add-instance` (no caption) and `sketch-discard-confirm` (a constant one). FIX: give each editor a `*SubmitBlocker` in its feature module, define `canSubmitX` as `blocker === null` so the two cannot drift, and pass it as `disabledReason` — the shape `HemEditor` + `apps/web/src/features/ sheetMetal.ts` now demonstrate. Keep each string ≤48 chars: the footer cell is half a card wide (~19 chars a line) and a 74-char sentence measured five wrapped lines. ACCEPTANCE: a property test per editor — across every way its form can be invalid, a gated submit carries readable text AND that text is its accessible description; plus one e2e case proving it at 1280x800 with `elementFromPoint`, because a footer that is not pinned puts the sentence outside the card (measured on the hem). TERRITORY: `apps/web/src/components/*Editor.tsx` + `apps/web/src/features/*.ts`. agentType: frontend-builder. **CLOSED 2026-09-04 (frontend-builder), and the acceptance grew one clause the ticket did not ask for.** All fifteen have an `xSubmitBlocker` with `canSubmitX` defined as `blocker === null`; `fieldBlocker` in the new `apps/web/src/features/submitBlocker.ts` is the one shared piece (the blank-vs-wrong pair, fifteen real uses) and `edgeSelectorBlocker` the second (fillet + chamfer). Evidence in three layers: 84 unit cases cross-checking every blocker against the PRE-change predicate restated literally (asking `canSubmitX` would be the new code agreeing with itself), with floors of 15 subjects / >=2 gated states each / >=50 gated total; a per-editor DOM case for all SEVENTEEN with the count asserted; and 10 editors measured in real pixels at 1280x800 with `elementFromPoint` resolving to their own Save cell. THE CLAUSE THAT GREW: every one of the fifteen action rows also had to move into `EditorCard`'s pinned `footer`. That slot has existed since UI-REVIEW 2026-07-30 P1 and only hole + hem used it, so a reason line — which makes each card taller — would have shipped the defect in a longer form; `docs/screenshots/reason-gate-draft- before-1280.png` shows the CREATE row half-clipped at the fold with nothing said. Mutation evidence: deleting `disabledReason` from ONE editor reddens exactly its own case and leaves sixteen green; un-pinning ONE footer reddens only that case. The e2e suite caught a copy defect the unit tests could not — the corner relief's first reason repeated its own FIELD's inline error verbatim, so the same sentence rendered twice on one card (a `getByText` resolved to two nodes); it now says "Choose a different flange for bend B." 2271 web + 141 design unit tests, 109 e2e. [src: HEM-1B survey, frontend-builder 2026-09-04] **STRAGGLER CLOSED groom pass 27 (`17763b5`):** `OffsetPlanePanel` (the sketch flow's inline datum-offset form) was never one of the 15 editors this rollout enumerated — it gates `SketchStrip`'s commit button, not an `*Editor.tsx` module — so it kept a native `disabled` with no `aria-describedby` and dropped out of the a11y tree while gated. Now asks the same `datumSubmitBlocker({kind:"offset",...})` the datum editor uses and renders through the editors' own `PanelActionCell`. `offset-plane-reason.spec.ts` 2/2, red on the pre-fix tree.

<a id="item-qa-r3"></a>

### QA-R3

*kind: item-story*

The rail's keycaps are real buttons and tapping one works (tap `verb-hint-angle` -> the editor opens -> 30 deg applies). The block is upstream: a plain second tap REPLACES the selection and a 900 ms long press (dispatched as a real touch sequence over CDP) does the same — additive selection is Shift-click only. Measured: `TOUCH-ADDITIVE {"plain":"1 ent","held":"1 ent", "offers":["verb-hint-distance"]}`, so the rail can only ever propose single-entity verbs there and angle / collinear / symmetric_lines / midpoint are unreachable. Diameter (single-entity) is fine.

<a id="item-playwright-touch-1"></a>

### PLAYWRIGHT-TOUCH-1

*kind: item-story*

kind: capability (test infra). MEASURED: `apps/web/playwright.config.ts` defines a single default project with no `projects` array at all — no device emulation, no `hasTouch`/tablet profile. Every touch finding to date (QA-R3 here, plus the `hasTouch`-context probes scattered across `full-flow.spec.ts`, `import-remix.spec.ts`, `measure-pattern-qa.spec.ts`, `qa-reach-batch.spec.ts`, `qa-sel4/6/7-verify.spec.ts`) hand-rolls its own `browser.newContext ({ hasTouch: true })`, so touch coverage depends on an individual spec author remembering to add one — there is no standing CI signal for "does this regress on touch" the way there is for desktop. FIX: add a `projects` entry (e.g. a tablet viewport with `hasTouch: true`, `isMobile` as appropriate) so touch-relevant specs can opt in via `test.describe.configure`/project filtering rather than each hand-rolling a context; consolidate the existing ad hoc `hasTouch` probes onto it where practical.

<a id="closed-next-closed"></a>

### CLOSED

*kind: closed*

- [x] (P2, S) **CLOSED (frontend-builder, 2026-08-29) — the field MOVED rather than the call site being remembered.** `mateErrors` now lives on `AssemblySolve`, empty whenever `stale`, and `AssemblyTreePanel` takes `solve` instead of the raw `EvaluateAssemblyResult`, so it has nothing ungated left to read (it was reading `diagnosis.conflicting_mates` directly too, which the ticket did not name). A field that is not on `AssemblySolve` is a field a consumer can read raw — that, not another call-site audit, is what stops a ninth. Rows carry `data-mate-state` (`ok`/`conflict`/`unresolved`/`pending`) so "no fault" and "not yet known" are distinguishable. The matrix gains the consumer in three places: the seven superseded-path rows, the 2^6 invariant over all 63 stale combinations, and the ONE settled combination asserting `mateErrors` has length 1 — without which "empty whenever stale" would hold in a build where the field is always empty. Measured on the real stack at 25 ms across a superseding write: `pre-write [conflict,conflict] inked=2` -> `t+0 stale=true [pending,pending] inked=0` -> `t+861 [conflict,conflict] inked=2`. Mutations, each reverted: panel back on the raw evaluation -> 2 rows badged over a superseded solve at t+612/779/898 ms, by attribute AND by ink; `mateErrors` ungated -> 8 of 13 matrix cases fail. Gates: `just lint` 0, `pnpm -r test` 2291, 28/28 across eleven assembly/mate specs. **MATE-OBS-2 — `AssemblyTreePanel` badges mates from `evaluation.mate_errors`, so it can carry a superseded solve's error set through the same staleness window MATE-OBS closed.** kind: defect (same family as MATE-OBS, `6b26ff7` — that fix made `evaluation` null whenever `stale`; this is a consumer that still reads the field directly rather than through the staleness-checked accessor). Found while verifying `6b26ff7`'s "SEVEN paths" list — the tree panel's mate badge was not one of the seven audited call sites. UNDER-claims rather than over-claims (a badge could show a stale error, or fail to show a real one, for the same ~600-840 ms window), which is why it is P2 not P0/P1 like MATE-OBS was. FIX: route `AssemblyTreePanel`'s badge through the same `stale`-gated accessor `6b26ff7` introduced for the solve title block, rather than reading `evaluation.mate_errors` directly. ACCEPTANCE: a mate write in flight shows no badge (or a clearly "pending" one) rather than the pre-write error set; the `6b26ff7` staleness matrix gains this consumer as an eighth case. [src: MATE-OBS (`6b26ff7`) follow-up, filed by backlog-groomer pass 15] TERRITORY: `apps/web/src/components/AssemblyTreePanel.tsx`, `apps/web/src/features/assemblySolve.ts`. agentType: frontend-builder.

<a id="item-stage-doc-hunks-heading-1"></a>

### STAGE-DOC-HUNKS-HEADING-1

*kind: item-story*

kind: defect (tooling — the fourth silent failure of this script, all four catalogued in CLAUDE.md's staging-protocol section; this is a new TRIGGER for the same "invented boundary" failure mode CLAUDE.md already records for a bold-continuation line). MEASURED: the PANEL-DENSITY-1 agent's marker landed on a `###` heading, and the entry's own BODY was a `- **ID**` list item directly beneath it — `ENTRY_START` reads a list item as always starting a new entry, so it split the agent's own 10-line body off from its heading and staged only the heading, printing `left 0 hunk(s) unstaged` while the body sat unstaged for nobody (the agent, not a colleague, so nothing was swept — but the commit shipped with a decapitated entry until caught by `git show :docs/BACKLOG.md`, the doc-hygiene check the staging protocol already mandates). FIX: teach `ENTRY_START` (or the cross-check) that a list item directly beneath a heading with no intervening blank line continues that heading's entry rather than starting a new one — the same "an entry boundary only opens where an entry CAN begin" principle the bold-continuation fix already applies, extended to the heading+list-item shape.

<a id="closed-next-drawing-vertex-pick-1"></a>

### DRAWING-VERTEX-PICK-1

*kind: closed*

**DRAWING-VERTEX-PICK-1 is CLOSED (`fe96d9b`, groom pass 16) — a vertex now claims at most a third of its shortest incident edge (`vertexGrabMm`), so the edge reclaims the band it lost. See Done archive.**

<a id="item-sketch-coverage-1"></a>

### SKETCH-COVERAGE-1

*kind: item-story*

kind: defect (test gap, on the class CLAUDE.md's params- extra-ignore recipe warns about: a UI path that silently regresses is indistinguishable from one that never worked). `SKETCH-VOCAB-1` closed the five verbs that were genuinely unauthorable (angle/diameter/midpoint/collinear/symmetric); `equal` and `tangent` predate that work and are believed reachable from the existing constraint menu, but a repo-wide spec search found no e2e case authoring either through the sketch UI (verify against `apps/web/e2e/sketch-*.spec.ts` before writing — do not assume the gap is real without re-checking, the same discipline `PATTERN-1`'s params-typo lesson demands).

<a id="item-solver-doc-1"></a>

### SOLVER-DOC-1

*kind: item-story*

kind: defect (documentation accuracy — CLAUDE.md: "a claim that is not true is a defect here, including in a comment"). MEASURED (`1ae3270`'s own investigation, deliberately NOT asserted in that gate): the LM solver slides a mated bracket ~0.015 mm laterally inside the mate's null space — deterministic, and not incorrect (those DOF are genuinely free), but it contradicts the docstring's anchoring claim. FIX: correct the docstring to describe what the solver actually does (converges to A solution within the null space, not necessarily the seed) rather than what was assumed.

<a id="item-flow-polish-1"></a>

### FLOW-POLISH-1

*kind: item-story*

Each independently shippable; pull by finding id and re- derive acceptance from the finding text. **P1** — a `422` with a `details[]` array renders as the generic envelope message ("Request validation failed") instead of the per-field reason the gateway already returns (T-2: registering `audit4@loft.test` fails with no indication the problem is a reserved-TLD email — the exact first interaction an air-gapped-shop evaluator would have). **P2** — after a drag-drawn rectangle, `document.activeElement` is `BODY` instead of the size cell 800px away in the corner that reads "Type a size" (T-4, half of FB-16's "capture intent where it forms" promise); the selection readout counts entities (`3 ents`) but never names them, so a refused selection (e.g.

<a id="item-import-heal-1"></a>

### IMPORT-HEAL-1

*kind: item-story*

kind: capability. `geometry.kernel.imports` says plainly "It does not sew/heal/repair, and IGES is deferred." Real supplier/legacy STEP frequently arrives with gaps, tiny faces, or open shells; a file yielding zero solids returns `import_no_solid` with NO recovery — no "import as surfaces", no "attempt to sew", no partial result. Preserve the audit's framing: this is the more SEVERE gap (an unrecoverable dead end — with a missing export format you convert elsewhere, with a dead import you cannot start at all) even though the audit ranks it P2 by COST against the near-zero DXF/3MF/glTF wins in Ready — that tension is deliberate, not an oversight. FIX: attempt OCCT `ShapeFix`/`ShapeUpgrade` sew+heal before returning `import_no_solid`; on success, the response carries a `repaired: true` flag naming what was fixed (faces stitched, gaps closed).

<a id="item-import-heal-2"></a>

### IMPORT-HEAL-2

*kind: item-story*

kind: capability. Depends on IMPORT-HEAL-1's response shape landing first.

<a id="item-export-err"></a>

### EXPORT-ERR

*kind: item-story*

kind: defect. Measured (`docs/AUDIT-PRODUCT.md` F-7, 2026-08-17): asking for a format outside `ExportFormat`'s literal (3MF/glTF have since shipped via EXPORT-2 and no longer trigger this — the example is stale, the underlying gap isn't: try `dwg` or `obj` today) gets `{"type":"literal_error","loc":["body","format"],"msg":"Input should be 'step', 'stl', '3mf' or 'glb'"}` — correct, but reads like a schema violation rather than "not built yet," which matters for anyone driving the API from a script or an agent.

<a id="item-solve-2"></a>

### SOLVE-2

*kind: item-story*

kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` R-3, 2026-08-21 pass): both are technically true (the solve converged; six DOF remain) but a user scanning "is this locked down?" gets a yes and a no at once, ~500px apart, with no cue which cell answers the question. Incumbents publish ONE status. FIX: the tree cell should carry the DOF verdict too, or drop the word SOLVE there and say `Converged`/`Failed`.

<a id="closed-next-pattern-1"></a>

### PATTERN-1

*kind: closed*

**PATTERN-1 is SHIPPED (`ec9c569`) — see Done archive for evidence/gates.** Its own design review found four flow gaps the builder did not catch; filed below as REACH-2-FLOW rather than reopening PATTERN-1 itself.

<a id="closed-next-reach-2-flow"></a>

### REACH-2-FLOW

*kind: closed*

**REACH-2-FLOW is CLOSED (2026-08-28, frontend-builder) — the pattern-scope proposal now has a channel the icon tier cannot shed (a `BandStateCell` primitive outside any `ToolGroup`, 104px painted vs 0px for the shed Modify label), three surfaces echo the subject (tree stamp, timeline chip, viewport tint via `usePublishedScope`), Cancel/Escape no longer destroys the triggering selection, and the row's context menu offers `Repeat`/`Mirror` directly so selecting a pattern seed no longer requires opening and dismissing its editor first. Mutation-tested per sub-defect. Two halves deliberately deferred, not forgotten — REACH-2-FLOW-B (viewport highlight should follow command scope, not just selection) and REACH-2-FLOW-C (tree select/edit split + band budget) below. See Done archive.**

<a id="closed-next-reach-2-flow-b"></a>

### REACH-2-FLOW-B

*kind: closed*

- [x] (P2, S) **REACH-2-FLOW-B CLOSED (2026-09-04, frontend-builder) — the viewport tint now answers the COMMAND's question, and the three surfaces agree.** The tint read `selectedFeatureId`, so it went on saying `Hole1` after the user flipped the scope row to `This body` and said nothing when the editor seeded from the TIP with nothing selected. `viewport/ scopeHighlight.ts` is the one rule both cases read; `PartPage`'s `selectedFaceIndices` filters the overlay by that set. THE FIX IS A THIRD STATE, not a fallback on emptiness: `scopedFeatureIds` was `readonly string[]` where `[]` meant BOTH "the whole body" and "nobody is asking", which the tree and timeline can conflate (no fallback, same absence) and the viewport cannot — it is now `readonly string[] | null`. `This body` paints NOTHING, chosen: a highlight is a differencer, so a full-body brass would hide the machined read, collide with the distinct whole-body SELECT state, and carry as much information as none. Measured in painted pixels (warmth census — the tint MULTIPLIES the matcap, so no literal hex describes it), same camera either side of the flip: scoped **384** warm px / `data-selected-faces` 1, `This body` **0** / 0, and tip-seeded with nothing selected **473** / 1. Mutation-tested per half: the pre-fix reading gives 384/1 on `This body` (the tint that would not let go) and 0/0 tip-seeded (the tint that never arrived). Screenshots: `docs/screenshots/reach2b-scope-{body,tip}-{before,after}-laptop.png`.

<a id="item-reach-2-flow-c"></a>

### REACH-2-FLOW-C

*kind: item-story*

kind: defect (flow). Two findings from REACH-2-FLOW that are each too large to be a clause of it, with the measurements that size them. (1) **The select/edit split.** `selectFeature` unconditionally opens the row's editor, which locks both the band (`sr-only`) and the accelerators, so "select Hole1, press Pattern" really costs an Escape. Fusion/Onshape/SolidWorks all separate single-click-selects from double-click-edits, and our row button is already NAMED `Select <name>`, so the destination is not in doubt. The cost is: **75 references across 28 e2e spec files**, roughly half of which click a row expecting an editor — a re-training event for every existing flow, not a sub-clause. REACH-2-FLOW shipped the narrow half instead (the row's context menu offers `Repeat`/`Mirror` directly, so the toll is gone for the seed gesture) and this is the general fix. Ship the second affordance in the SAME commit or editing becomes undiscoverable: double-click, Enter on the focused row, and the existing `tree-ctx-edit`. (2) **The band's budget.** Measured at 1280x800: the resting row is 1241px of 1280, i.e. **39px of slack**, and the label budget affords exactly EXPORT (+160) and INSPECT (+37). Any always-visible cell therefore drops the band to the icon tier — REACH-2-FLOW's 104px scope cell does, costing EXPORT its format codes while a scope is held (it gets them back the moment the cell's `x` is pressed, measured). `CommandBand`'s own doc names the fix: an explicit overflow flyout. A cheaper prize sits beside it — SHEET METAL is 215px of icons for a family "inert on every part that is not sheet metal".

<a id="closed-next-ortho-1"></a>

### ORTHO-1

*kind: closed*

**ORTHO-1 is CLOSED (`9a04a6a`, groom pass 16) — an ORTHO/PERSP toggle in the view rail; orienting commands (Home/Front/Top/Right/Iso, their accelerators, ViewCube picks) arm orthographic, Fit does not change it, orbiting away from a named view keeps it. Closes a gap four consecutive audit passes reported (M18/R-11/S-31/T-20). See Done archive.**

<a id="closed-next-hem-1"></a>

### HEM-1

*kind: closed*

**HEM-1 is CLOSED (`db05e13`, P0, groom pass 17) — a "closed" hem's radius now comes from the hem type and gauge (~0.5x thickness), not the part's general bend radius. See Done archive for evidence/gates.**

<a id="closed-next-closed-2"></a>

### CLOSED

*kind: closed*

- [x] (P1, S) **CLOSED (frontend-builder, 2026-08-29) — RENDERING ONLY; the server already sends this typed, so no larger ticket is owed.** `AssemblySolveDiagnosis` carries `classification`, `conflicting_mates`, `redundant_mates`, `remaining_dof`; `message`/`suggested_fix` are prose built ALONGSIDE them and the panel was printing the prose. Nothing in `services/geometry` changed. `apps/web/src/assembly/diagnosis.ts` composes the sentence from the typed fields and never reads `message`, naming mates through `mateNamesById` — the same derivation the tree prints on the row, so a raw id can never be the only handle because it is never printed at all (an id with no row is COUNTED, never printed). `sentence()` terminates each clause before joining, closing (c) here and on the healthy path. Mates gained the handle they lacked: `M1`, `M2` … in a squared tag (components are balloons/circles; a joint is not a part), numbered in the solver's own processing order, not `aria-hidden`, and the row's Remove is now `Remove M2 Coincident` so two mates of one kind no longer share an accessible name. The "remove this one" action ships HERE rather than as its own item — the handler existed and the message is one line above it; the chip spends the tag only (`Remove M1`, full form as accessible name) because the longer label stacked the chips and pushed BOUNDING BOX below the fold at 1280. Gates: 19 unit + 3 e2e new, `just lint` 0, `pnpm -r test` 2290, 24/24 across eight assembly specs. Mutations, each reverted: server prose restored -> the e2e reproduces the reported string verbatim; visible tag deleted with `data-mate-tag` kept -> the findability case fails on the INK, not the attribute; `sentence()`'s terminator dropped -> 11 of 19 unit cases fail with the exact run-on. Frames: `docs/screenshots/mateui1-before-1280.png` / `mateui1-after-1280.png`. **MATEUI-1 — the mate-conflict diagnosis prints a Python `repr` of a UUID list to the user, and names a mate the UI cannot identify.** kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" S-18), verbatim from the SOLVE tab with two conflicting Coincident mates: `mates [UUID('4ae95465-...'), UUID('b78a814e-...')] are mutually unsatisfiable Remove or relax mate 4ae95465-...` — (a) a raw list-of-UUID repr leaked into user-facing UI; (b) the named mate appears NOWHERE in the mates panel (both rows read identically as "Coincident · ①1 · ②2 · conflict"); (c) two sentences concatenated with no separator — same missing-separator bug on the healthy path too ("...remain; free instances left at their seed placement Add mates to..."). FIX: render the typed diagnosis as data — name mates as they appear in the panel (or add a distinguishing label so a UUID isn't the only handle), fix the missing sentence separators everywhere they occur, add a "remove this one" action next to each named mate. ACCEPTANCE: the conflict message names mates by their panel-visible identity, not a UUID repr; a unit/snapshot test on the message-assembly function catches a reintroduced missing separator. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)" S-18, filed by backlog-groomer pass 9] TERRITORY: assembly mate-conflict diagnosis rendering, `apps/web/src` (assembly inspector SOLVE tab) + `services/geometry/src/geometry/ assembly/**` (message assembly, if server-formatted — check first). agentType: frontend-builder (or backend-builder if the string is assembled server-side).

<a id="closed-next-closed-3"></a>

### CLOSED

*kind: closed*

- [x] (P1, XS) **CLOSED BY MEASUREMENT (frontend-builder, 2026-08-29) — DOES NOT REPRODUCE ON HEAD; T-18's `ScrollRegion` (`a67f4bc`) and the density pass (`54d12bf`) had already fixed it and nobody re-measured, so this was one groom pass from being fixed twice.** Re-measured at 1280x800 on the audit's own subject (150x80x8 plate, steel assigned): band y=112..474.5, strip y=474.5..590 — **abutting at 0.0 px against the reported 73 px overlap** — and all 8 on-screen rows resolve to THEMSELVES under `elementFromPoint`, `Extents` included. The 137 px below the fold is clipped, marked and keyboard-reachable (T-18's shipped answer). NOTE the trap: a naive rect-vs-rect sweep "reproduces" this on a healthy panel, because a row below the fold keeps its layout rect — 8 of 10 rows report an overlap that is only a scroll away. Shipped instead: the ticket's own acceptance criterion as a permanent clip-aware gate in `apps/web/e2e/inspector-scroll.spec.ts` (band/strip never intersect; strip never hangs past the panel; every on-screen row answers to itself; count floor 6 against a vacuous pass). Two mutations, each reverted and each with Vite restarted + served bytes re-read, turn it red — the `FloatingPanel`-footer one reproduces the audit verbatim (`prop-faces` on screen, `elementFromPoint` → `part-export-controls`). No product code changed. Frames: `docs/screenshots/layout1-reported-defect-1280.png` vs `layout1-inspector-1280.png`. **LAYOUT-1 — the inspector panel overlaps its own content at the documented responsive floor (1280x800), violating CLAUDE.md's stated quality floor directly.** kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" S-29): `getBoundingClientRect` at 1280x800 — `BOUNDING BOX` section y=410…532, export band (`part-export-controls`) y=459…590, a 73 px overlap; the `Extents` row is half-covered by `EXPORT Ready`. Min, Max, Faces, Edges, Shells, Status are unreachable. FIX: resolve the layout collision (stack, scroll, or resize) at 1280x800. ACCEPTANCE: a layout assertion (Playwright bounding-rect check, mirroring S-29's own method) at 1280x800 confirms zero overlap between the inspector's sections; visual regression screenshot at that width. [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-21 (second pass today)" S-29, filed by backlog-groomer pass 9] **THIRD CORROBORATION, groom pass 11 (2026-08-24): T-18 (fourth product pass) re-measured the identical overlap on a finished part — `Min` row at y 474..491, export panel at y 459..589, `elementFromPoint(985, 482)` returns the Export panel's own `SPAN`, and walking the ancestor chain finds NO `overflow: auto|scroll` container, so the content is unreachable by scrolling either.** [src: docs/AUDIT-PRODUCT.md "Pass 2026-08-24 (fourth pass)" T-18] TERRITORY: apps/web inspector panel component (grep `part-export- controls` / `BOUNDING BOX` section). agentType: frontend-builder.

<a id="closed-next-closed-4"></a>

### CLOSED

*kind: closed*

- [x] (P1, XS) **CLOSED (frontend-builder, 2026-08-29).** A body with no stop of its own now ghosts while a sketch is open, via a DERIVED DEFAULT (`partView.bodyView`) on the same contract `sketchIsDrawn` has held since UI-W2 — nothing is written on entry, so there is no restore step on exit to get wrong, and a stop the modeler SET wins at every moment including one set mid-sketch, which then survives the close. Applies to EVERY body (occlusion follows the camera and the plane, not the picked face); `hidden` never moves, so isolate / show-all / the ISOLATED stamp / pick-occlusion are untouched. One derivation feeds the Bodies row AND the material split, and `sketchOpen` is a required argument — which is what surfaced every call site at compile time. Published by `SketchScene` on `draw`, not `plane`. No new token (existing `viewport.preview.surfaceOpacity` 0.42). MEASUREMENT TRAP, recorded because the first draft fell in it: the canvas band census cannot be compared across sketch entry/exit (the sketcher parks the camera; BRIGHT 310289 -> 24675 with drawn=6/ghost=0 at both ends), and the bands cannot separate ghost from solid even at one camera head-on (26935 vs 27299, 1.3%). The working instrument is the SPECULAR PEAK (lum > 210): ghosted 0/0, solid 525. Gates: partView unit 25/25, part-visibility 9/9, 23/23 sketch specs, 19/19 body/pick specs, `just lint` 0, `pnpm -r test` 2270. Mutation (`bodyView` ignores `sketchOpen`, Vite restarted + served bytes checked) reddens the new e2e case and 2 unit cases. Frames: `docs/screenshots/ghost1-sketch-open-{before,after}.png`. EVIDENCE PASS (same day, follow-up): the cube pair was correct and did not COMMUNICATE — head-on, ~8% of frame, and the only occluder is the sketch's own body, so it cannot tell "ghost the host" from "ghost everything". Added `a NEIGHBOUR body ghosts too`: a two-body part whose HOST is extruded `direction: "reverse"` (behind the sheet, occludes nothing) with a `merge: false` bar standing in front of the profile — the configuration the scope decision was made for, and one a host-only build would fail. It orbits off the sketch normal for depth, and three things had to be measured: dragging into the park-ease loses the orbit (settles 0.02 deg from straight down, reads as an unbound button — wait for camera rest first); the documented (150,-110) drag turns 72 deg and is unreadable, (62,-46) gives 31.56 deg; and `waitForCameraRest`'s 0.05 deg default is unreachable against a coast that decays per rendered frame (0.3 deg settles). The settled pose is reproducible to 1e-12 and is PINNED in the spec, because the pair is shot in two runs and is only honest on one camera. Frames: `docs/screenshots/ghost1-neighbour-{before,after}.png`. FOLLOW-UP FILED, not fixed here: exiting a sketch leaves the camera parked in the sketch's TOP view instead of restoring the previous view (pre-existing, unrelated, found while measuring) — see CAMRESTORE-1. **RESIDUAL CLOSED groom pass 27 (`0d96454`):** `ModelMesh` returned before ghosting anything whenever a part's per-body face split couldn't be resolved (two bodies welded at shared coordinates — `bodyFaceSets` -> null), so such a part stayed fully OPAQUE over the sketch being edited even though the Bodies panel correctly read GHOST. Fixed: ghost the WHOLE mesh when no split exists and no body carries a stop of its own (a stored stop still wins). Pixel witness asserted first (bright fraction inside the plate's top face: 1.0 on the pre-fix tree, 0.0 after); 22/22 regression across part-visibility, multibody-disjoint/union and sketch-visibility.

<a id="item-stepname-1-2"></a>

### STEPNAME-1

*kind: item-story*

kind: defect. MEASURED (`docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" S-22): STEP structure is correct (1 assembly PRODUCT, 2 NEXT_ASSEMBLY_USAGE_OCCURRENCE, exact volume) but read back through OCCT's XCAF reader the component labels are raw UUIDs (`c7ebc346-bbd5-4f55-9a01-4fce6f5fc28e`); the instance's real name ("Chassis bracket") is right there in the BOM and unused. Also: `FILE_NAME` still reads `'Open CASCADE STEP processor 7.9', 'build123d','Unknown'` — Loft doesn't name itself in files it authors. FIX: use the instance/part name for each component label in the STEP writer; set the originating-system field to identify Loft.

<a id="closed-next-stepname-1b"></a>

### STEPNAME-1B

*kind: closed*

- [x] (P1, XS) **STEPNAME-1B — the web builds the assembly evaluate request without the instance `name`, so every user-facing STEP export falls back to the UUID.** DONE 2026-08-29 (frontend-builder). One line — `name: instance.name` — and the evidence that it means something. **Asserted on the exported bytes, never on a 2xx**: `apps/web/e2e/assembly-step-names.spec.ts` builds a part named `Flänsch`, instances it twice through the real UI, clicks the real STEP cell, and parses the part-21 text with the same `_LITERAL` rule the kernel suite uses (both escapes undone, then UTF-8 decoded — a substring check would have passed on the mojibake `6c52d5f` fixed). Occurrences read `["Flänsch <1>", "Flänsch <2>"]`, the part gets ONE shared `PRODUCT('Flänsch')`, and NO name in the file matches a UUID. **Mutation evidence**: with the line reverted the same spec reports `["9ed8bc86-…", "1a8c2497-…"]` — the audit's exact symptom, reproduced — and the unit case reddens to `[undefined, undefined]`. The name is sent VERBATIM (`"<part> <n>"`): the writer's contract puts the whole name on the NAUO and the suffix-stripped form on the shared PRODUCT, so pre-stripping client-side would have split one part into N PRODUCTs. Acceptance's last clause checked: `buildEvaluateAssemblyRequest` is the web's ONLY evaluate-request builder, so interference is fixed by the same line (it ignores the field), and the assembly drawing path builds no such request at all — it goes through documents, which has always sent the name. Gates: `just lint` exit 0, `pnpm -r typecheck`, `pnpm -r test` (2130 + 141), 13/13 assembly + export e2e green on an isolated native stack. This is STEPNAME-1's ACTUAL headline cause, isolated by the kernel-architect on 2026-08-29 after measuring that the geometry writer has carried names correctly since `0d3ea59`. `apps/web/src/assembly/evaluateRequest.ts`'s `buildEvaluateAssemblyRequest` maps each instance to `{instance_id, part_key, grounded, placement, features, materials}` and omits `name`, which `EvaluatedInstance` has had (optional, defaulting to `None`) since the naming work landed. `services/documents` DOES send it (`assemblies.py` `build_evaluate_assembly_request`, `name= instance.name`), which is why the defect is invisible from the backend and why the audit — exporting through the app — saw UUIDs. **Watch the class, not just the line:** an optional DTO field the producer silently omits is the same shape as the `extra="ignore"` typo trap in CLAUDE.md — everything validates, evaluates and returns 2xx while meaning nothing. ACCEPTANCE: `name: instance.name` threaded through; a test that asserts on the EXPORTED BYTES (or a re-import), never on a 2xx — `services/geometry/tests/test_step_names.py` has the part-21 literal parser to borrow, including the two escapes a naive `[^']*` gets wrong; the audit's two-part assembly exports with both components named. Check the drawings/interference callers for the same omission while you are there. [src: STEPNAME-1, kernel-architect, 2026-08-29] TERRITORY: `apps/web/src/assembly/evaluateRequest.ts` + its unit test. agentType: frontend-builder.

<a id="closed-next-stepname-2"></a>

### STEPNAME-2

*kind: closed*

- [x] (P2, S) **STEPNAME-2 — CLOSED (kernel-architect, 2026-09-04). Option (a): the single-body export now writes through the SAME owned writer as the assembly path, and unifying cost nothing a consumer can see.** The defect, measured on the bytes for a part named "Flänsch 40°": `PRODUCT('FlÃ\x83Â¤nsch 40Ã\x82Â°')` and `FILE_NAME(...,'build123d','Unknown')` — the SAME two defects STEPNAME-1 fixed for the assembly, on the export a user reaches by downloading one part, i.e. the common path was the broken one. **THE DECISION, since this ticket was mostly a decision.** The worry that made (a) a judgement call was that owning the writer would drag XCAF assembly structure into a file with none, changing the emitted shape for every user and moving every digest. **It does not** — `_single_body_xde_document` rebuilds the document build123d's `_create_xde` builds for a shape with no children (`makeAssembly=False`, auto-naming ON) and the payload is BYTE-IDENTICAL to build123d's for a named solid (15 348 B), an unnamed solid (15 335) and a multi-body `Compound` named (29 169) / unnamed (29 193). The complete before/after diff of the shipped fix is the originating-system field plus, for a non-ASCII name, the `PRODUCT` id/name — nothing else. **No golden's content hash moves**: the sheet-metal `content_hash` values are sha256 of `FlatPattern.to_json_bytes()`, and nothing in the suite pins a digest over single-body STEP bytes (checked, not assumed). **Mutation evidence, four mutants, all restored:** encoding reverted -> 8 red (all and only the non-ASCII names x both `BodyShape` members; the three ASCII-punctuation shapes stay green, as part 21 always handled them); whole path back to `build123d.export_step` -> 10; the "unnamed keeps OCCT's default" skip dropped -> 1; and the negative control for the structural claim, `makeAssembly=True` -> 12, including the byte-determinism gate, because turning a part into an assembly reintroduces STEPDET-1's process-global counter. Only the MULTI-BODY cases fail under that control — the same blind spot STEPDET-1 paid for. Also: the export no longer mutates the caller's shape (it used to borrow `shape.label`). Filed from the measurement: STEPHDR-1 (P3). [src: STEPNAME-1, kernel-architect, 2026-08-29; closed 2026-09-04] TERRITORY: `services/geometry/src/geometry/kernel/export.py` (`export_step_bytes`). agentType: kernel-architect.

<a id="item-stephdr-1"></a>

### STEPHDR-1

*kind: item-story*

kind: defect. `FILE_NAME`'s NAME field is set through `TCollection_HAsciiString`, which is byte-transparent, so `export_step_bytes(..., name="括号 A")` writes the raw UTF-8 bytes into a header ISO-10303-21 defines over ISO-8859-1. Measured 2026-09-04 (STEPNAME-2): it round-trips byte-exactly under a UTF-8 decode, and every reader we have tried is UTF-8-tolerant, but a strict reader would show mojibake. **P3 for two reasons, both worth keeping in the record.** (a) It is IDENTICAL in the part and assembly paths — `_write_step_document` is the single call site — so this is not a re-creation of the part/assembly split STEPNAME-2 closed, and fixing it fixes both at once. (b) The header NAME is provenance metadata; the field a downstream tool actually keys on is `PRODUCT`, which is correct in both paths as of STEPNAME-2.

<a id="closed-next-stepdet-1"></a>

### STEPDET-1

*kind: closed*

- [x] (P1, S) **STEPDET-1 — CLOSED (kernel-architect, 2026-08-29). The canonicalisation is one pattern and a shared helper; the fixture that makes the gates able to fail is the deliverable.** `_canonicalise_occurrence_ids` is now `_canonicalise_writer_counters` and renumbers BOTH process-global counters through one shared `_renumber_in_appearance_order` — an extension, not a second parallel mechanism. `goldens-assembly/assembly-two-multibody-brackets` is the bolted golden verbatim (same instances, mates and seed) plus one disjoint 10 mm cube per part, so the joint's reviewed analytic answer carries over and multi-body is the only new variable; hand-derived, measured deviations volume **0.0**, area 1.8e-12, centroid <= 1.1e-09, solved z 1.18e-08 against a documented 1e-6. It is ASSERTED to reach the `Compound` path (2 translator PRODUCTs, 2 B-reps for 1 unique part, 4 NAUOs for 2 instances) rather than assumed. **Mutation:** reverting the canonicalisation reddens 4 cases (both determinism gates on the new golden, its counter-pinned byte assertion, the naming suite's in-process one) while 54 pass — including every determinism case of both older goldens in all four formats, which is the blind spot measured. `At index 4024 diff: b'1' != b'2'`. Two neighbouring gates carried the same "one part is one solid" assumption and rejected the new golden (`2 B-reps written for 1 unique part(s)`); both are now per-BODY. The recorded live limit in `test_step_names.py` is deleted and replaced by its positive form. No golden's content hash moves: a FIRST export in a process was already counter-1, so the fix changes only the repeat export (verified legacy-vs-new byte comparison, all three goldens). Gates: full geometry suite green, `just lint` 0, pyright clean; no DTO touched. STEPNAME-2 is unaffected — measured, the single-body path builds no XCAF assembly and is already byte-stable. Original entry follows. kind: defect (determinism, RESEARCH §9). Found by STEPNAME-1 (2026-08-29) while writing a determinism assertion for its own change — the assertion failed, and not for the reason expected. When a component's body is a `Compound` (i.e. a multi-body part, MB-0, an ordinary thing to instance), OCCT wraps it in an extra unnamed assembly level and names that level's PRODUCT `'Open CASCADE STEP translator 7.9 N.M.K'`, where **N is a process-global write counter**. Two exports of the same assembly in one worker differ — measured, first difference at byte 3462, `1.1.1` vs `2.1.1`. Reproduced deterministically by `test_a_multi_body_part_makes_the_export_non_deterministic`, which asserts in the FAILING direction so closing the gap reddens the suite. **Why nothing caught it:** it is exactly the defect `_canonicalise_occurrence_ids` already fixes for the NAUO id, in a second byte range nobody looked at, and BOTH shipped assembly goldens are made of single `Solid` parts, so the extra level never appears in them. `test_assembly_export`'s in-process AND interpreter-restart determinism gates therefore pass while the property is false — the archetypal gate that cannot fail for the reason you care about, and the reason the fix needs a GOLDEN, not only a canonicaliser. Impact: a worker re-exporting an unchanged assembly returns different bytes, so any content-addressing over the artefact misses. ACCEPTANCE (all met): a multi-body assembly golden lands FIRST and is shown to fail the existing in-process + restart determinism gates (the negative control); the counter is then canonicalised the same way the NAUO id is; both gates go green on it; the recorded live limit in `test_step_names.py` is DELETED in the same commit and the deletion is stated in the message. [src: STEPNAME-1, kernel-architect, 2026-08-29] TERRITORY: `services/geometry/src/geometry/kernel/export.py` (`_canonicalise_occurrence_ids` and its neighbours), `services/geometry/goldens-assembly/`, `services/geometry/tests/test_assembly_export.py`, `services/geometry/tests/test_step_names.py`. agentType: kernel-architect.

<a id="closed-next-signin-1"></a>

### SIGNIN-1

*kind: closed*

**SIGNIN-1 is SHIPPED (`bf65ddc`) — see Done archive for evidence/gates.**

<a id="item-sm-polish-1"></a>

### SM-POLISH-1

*kind: item-story*

Each is small, independently shippable, and cited by finding id in `docs/AUDIT-PRODUCT.md` "Pass 2026-08-21 (second pass today)" — pull the one you're building and re-derive acceptance from the finding text before starting: **P2** — continue the rebuild past a failed feature for features that don't depend on it (S-24); four orientation view-bar buttons share one icon, byte-identical SVGs (S-30); flange-length/hem-return has no stated datum (S-8/S-12); sketch dimensions render as bare numerals with no extension lines/arrowheads (S-35); per-instance appearance + non-interpenetrating seed placement in assemblies (S-16); auto-layout should fill the sheet at the largest fitting scale and suppress trailing zeros (S-28); Measure needs diameter/radius/centre-to-centre (S-33); STEP import at 12.1 s for an 18-face part is the one performance outlier (S-37 area). **P3** — export the full title string, not a UI- truncated ellipsis (S-14); sheet-metal recognition on an imported solid (S-37); contact shadow + edge overlay on shaded solids, and drop the decorative empty rows on an empty register (S-33/S-2); opening a newly created assembly should navigate into it, matching part-create (S-17).

<a id="item-gqa-1"></a>

### GQA-1

*kind: item-story*

kind: defect (a design-doc overclaim plus a real, if narrow, resolver gap — NOT a regression of `1e39c14`/GEOM-3: tier 4b admits the same wrong face identically, so this predates GEOM-3 and GEOM-3 neither introduced nor closed it). All three invariants are exactly preserved under any rigid ROTATION of the wire about its own centroid, so two congruent-but- differently-oriented faces sharing an in-plane centroid agree on all three and tier 4a wrongly admits either for the other. MEASURED (`docs/GEOMETRY-QA.md`, 2026-08-16 GEOM-3 independent verification): a 100x40/40x100 transition-bracket flange pair, both `A=4000.000 P=280.000 C=(0,0)`, resolves to the WRONG face — `resolve_face_plane -> origin (0.0, 0.0, 10.0)`, a **40.000 mm silent error** at the resolver level. Severity kept at P2 not P0: three independent attempts to build a feature-tree vehicle that reaches this from an ordinary edit all hit real kernel guards (`cut_removed_nothing`, `boolean_failed`, `subshape_ambiguous`) — resolver-level reachability is proven, product-level reachability is not. FIX: (a) correct §12b's prose from "narrows congruent to the same outer wire" to "the same outer area, perimeter and in-plane centroid" and add the rotation/reflection family to the honest-limits list; (b) the durable close needs an orientation-bearing invariant (the three scalars gated today are deliberately not one) — a second area moment or an anchored boundary hash, TBD by whoever picks this up.

<a id="item-sketch-3"></a>

### SKETCH-3

*kind: item-story*

Named and deliberately NOT built by the SKETCH-2 builder, with reasoning worth preserving rather than re-litigating: `withoutDatums` (`apps/web/src/sketch/datum.ts:182`) is id-based, so a foreign entity sharing one of the three reserved ids would be hidden from drawing and picking, and `groundDatums` (`datum.ts:237`) would pin it as though it were the real frame. A correct fix is not cheap — renaming on hydration risks references the client cannot enumerate (constraints, drawing views, mate authoring all cite entity ids by string), and a warning that only announces the collision without resolving it is decoration, not a fix. Exposure is THEORETICAL today: nothing external authors sketch JSON — Phase 5's scripting/MCP surface is the first path that would. FIX: once Phase 5 lands a write surface, either namespace the reserved ids out of the user-authorable range (e.g. a sigil no client-authored id can produce) or validate + reject/rename on ingest with full reference remapping.

<a id="item-fb-19"></a>

### FB-19

*kind: item-story*

The chrome-density fix (label-beside-control `FieldRow` primitive, compacted `NumberField`/`SelectField`/`Checkbox`/`SegmentedControl`, measured origin block 212.0px->95.0px, extrude card 368.3px->219.5px, tree panel 591.0px->474.0px, all against stated ceilings) is preserved and gate-passing at the unit level only (typecheck, 1618 web + 86 design unit tests, prettier/eslint clean) — the agent died before its own `fb19-chrome-density.spec.ts` e2e gate ran even once, and no `code-reviewer`/`qa-tester` pass has happened.

<a id="closed-next-founder"></a>

### FOUNDER

*kind: closed*

- [x] (P1, M) **FOUNDER — no Fusion-style hover-a-face-to-sketch.** DONE — rest the pointer on a face with nothing armed and the viewport writes a drafting LEADER NOTE (anchor dot + hairline stub + a `Sketch ↵` chip); click it or press Enter and a sketch opens on that face. It calls the SAME `handleNewSketch` + `authorFacePlane(face)` pair the toolbar flow calls — proven byte-identical at the wire by a new e2e case that records the `on_face` datum POST from BOTH paths for one face and compares them (ablation: perturbing the centroid by 1 mm reports `"z":10` vs `"z":11`). UX decided by the builder, per the item: the note is written on REST (`proposal.dwellMs` 320 ms) not on hover, so sweeping the model proposes nothing; the face's own SEL-1 tint carries the proposal and the chip only confirms it; and once written it LATCHES — travelling onto the chip takes the pointer off the mesh, and the first build withdrew the note in the instant the user reached for it. Keyboard: `Enter` accepts the showing note (declared in `shortcuts/registry.ts`, printed on the chip, on the key sheet); tabbing to named faces stays the Sketch command's job. Reachability measured, not assumed — `elementFromPoint` at the chip's centre resolves to the chip, and removing its `pointer-events` reports `"viewport"`. Founder shots: `docs/screenshots/hover-sketch-{before, after}-{1280x800,1600x1000}.png`, pixel-aligned pairs. ORIGINAL REPORT, for the record: complaint: today, starting a sketch requires clicking the Sketch command FIRST, then picking a plane/face; Fusion lets you hover an empty-context face and click a glow-in affordance to sketch on it directly, no prior command needed. Related to M4(a) (product-audit pass 2026-08-14): after a sketch is solved, the tool never proposes "Extrude this" either — both are instances of the same flow principle (CLAUDE.md design mandate: "the tool proposes, the user disposes"). Scope this item to the HOVER-TO-SKETCH half only (the extrude-proposal half is a separate, larger item — see the FLOW-1 flow umbrella below). MECHANISM: when no command is active and the body is interactive (`mode === "off"`, per `PartPage.tsx`'s `bodyInteractive` computation), hovering a face should show a small in-viewport sketch affordance (icon or highlight) near the cursor; clicking it calls the same `handleNewSketch` + face-plane-authoring path the toolbar Sketch command already uses (`authorFacePlane`, `PartPage.tsx:3260+`), pre-seeded with the hovered face. ACCEPTANCE: hover a face with no command active — an affordance appears within N px of the cursor; click it — a sketch opens on that face's plane with the same behaviour as Sketch → pick that face today (byte-identical resulting plane/params). New e2e spec. [src: founder report 2026-08-14, needs UX detail decided by builder; cross-ref product-auditor M4(a)] TERRITORY: `apps/web/src/routes/PartPage.tsx`, `apps/web/src/viewport/**` (hover affordance rendering), new e2e spec. agentType: frontend-builder. **Founder reports outrank everything — this is next up in `apps/web/src/viewport/**` once PICK-2/FB-21/FB-9/ SEL-8 clear that territory this batch (contention, not demotion).**

<a id="item-esc-3"></a>

### ESC-3

*kind: item-story*

The shipped `store.test.ts` "Escape disarms it and does NOT exit the sketch" asserts `mode === "draw"`, which passes even with the rung ABLATED, because with 4 entities in the sketch the `unstarted` branch is unreachable — a tautology w.r.t. the fix under test. MEASURED by ablation: armed with 4 entities and the rung removed, Escape leaves `mode: "draw"` (existing test stays green); armed with ZERO entities and the rung removed, Escape gives `mode: "off"` — the sketch is gone.

<a id="item-vp-1"></a>

### VP-1

*kind: item-story*

`NavCue` (`apps/web/src/components/NavCue.tsx`) renders only when `viewNav` is true, which is false while sketching, and its copy ("Drag orbits") would be wrong there anyway (LEFT is reserved for drawing). FIX: a sketch-mode variant naming the two real bindings (MIDDLE-drag rotates; Alt/Option+drag rotates). Note TOUCH remains uncovered separately (a touchscreen has neither a middle button nor a modifier key) — file separately if this item doesn't absorb it.

<a id="item-qa7-1"></a>

### QA7-1

*kind: item-story*

Measured by the reviewer: each shape applied then reverted, 1 passed — the gate does not fire. Neither shape exists in `qa-sel7-verify.spec.ts` today, so nothing is unguarded right now, but the gate's own header claims a completeness the code does not meet — this repo's own guard-encodes-the-direction-of-its-defect pattern. Separately, the gate is scoped to one file rather than all of `apps/web/e2e` (sibling specs were other agents' territory when it shipped). FIX: widen the binding-recognition regex to cover `page.locator`/arbitrary-identifier forms, and either promote the scanner to cover every e2e spec or lift it into a standalone `just lint`-wired script (`scripts/`) so new specs inherit the guard without a per-file copy.

<a id="item-touch-1"></a>

### TOUCH-1

*kind: item-story*

`apps/web/playwright.config.ts` declares a single default (desktop Chromium, 1600x1000, `deviceScaleFactor: 1`) — no `projects` array, so there is no systematic touch/mobile run of any kind. The only touch coverage that exists is ad hoc: 6 spec files (`qa-sel4-verify`, `qa-sel6-verify`, `qa-sel7-verify`, `measure-pattern-qa`, `full-flow`, `import-remix`) locally override `test.use({ hasTouch: true, viewport: … })` inside one describe block each — a hand-picked subset, not a run of the suite. This is a PROCESS defect as much as a coverage gap: any brief (including this repo's own QA dispatches) that asks for "desktop and touch" verification cannot be honoured by "run the touch project," because none exists — it can only mean "if one of these 6 specs happens to cover it." FIX: add a `projects` array with at least one touch-emulating profile (`{ ...devices["iPad (gen 7) landscape"], hasTouch: true }` or similar) that runs a deliberately-scoped touch SMOKE subset (not the full 350+ spec suite doubled — sizing that subset is part of the work), wired into `e2e.yml` as its own shard/job so a touch regression has somewhere to show up.

<a id="item-touch-2"></a>

### TOUCH-2

*kind: item-story*

Measured by independent QA of SKETCH-2 (`c82ff09`, `docs/UI-REVIEW.md`). Related to TOUCH-1 (no touch Playwright project exists to have caught this) but a distinct product concern — the mouse pick tolerance (`PICK_TOLERANCE_PX = 8`) the ring rides on is well below WCAG 2.5.8's 24 px minimum, and unlike a drawn line a datum pin has no alternate keyboard-reachable affordance advertised anywhere in the UI (the SKETCH-2 QA found the keyboard Tab-to-origin path exists but undiscoverable). FIX: give the frame's hit region a touch-specific floor independent of the mouse pick tolerance (mirrors A7/SEL-1's existing pattern of a generous invisible hit area with a tighter visual mark).

<a id="item-qa-sk2-3"></a>

### QA-SK2-3

*kind: item-story*

`SketchStrip.tsx` disables the Finish button `disabled={saving || …}` for the duration of every constraint-edit's autosave; a click in that window is delivered to a disabled button and does nothing, with no feedback — measured always at `DOF 0 · CONVERGED`, i.e. the save had already succeeded. Pre-existing (not introduced by SKETCH-2), but SKETCH-2 put grounding-then-finish on the hot path so it is hit more often now. FIX: don't disable across a live save (it's already committed server-side), or queue the click and replay it when the save settles.

<a id="item-spec-6"></a>

### SPEC-6

*kind: item-story*

`measureReach` (`pick-affordance .spec.ts:150`) does `page.mouse.move(...)` then immediately `viewport.getAttribute(attribute)` with no wait for the React commit — the exact shape SPEC-5 (`c7d3f2a`) diagnosed and fixed at the hole-point call site, using an oracle that nulls the stamp against a known-off-body position first so a lag can't masquerade as a fresh read. Here the failure direction is the opposite of SPEC-5's (which under-read "on face"): a lagging read on `measureReach` INFLATES perpendicular reach against the fillet/measure/mate `<= 16 px` ceilings it feeds, i.e. it fails SAFE (hides a defect rather than reporting a false one) — which is exactly why nobody has been forced to notice yet. **CHECK FIRST**: a builder was live sweeping this file for zero-settle attribute reads as of this pass; before building a fix, confirm `measureReach` isn't already covered by that sweep.

<a id="item-spec-7"></a>

### SPEC-7

*kind: item-story*

Filed as a single data point per this repo's own rule against diagnosing load-dependent failures from few samples — the orchestrator has been wrong twice this session doing exactly that. No cause is claimed. **CHECK FIRST**: a builder was live sweeping this same file for zero-settle attribute reads as of this pass (see SPEC-6); this single failure may already be explained or fixed by that work — read `git log` for `pick-affordance.spec.ts` before treating this as open.

<a id="closed-next-x-p1-s-k7-stop-hook-in-fligh"></a>

### - [x] (P1, S) **K7 — Stop hook in-flight guard fixed. SHIPPE

*kind: closed*

- [x] (P1, S) **K7 — Stop hook in-flight guard fixed. SHIPPED 29387da 2026-08-14.** Depth-agnostic `find -path '*/tasks/*.output' -mmin -30`, `-print -quit` (the piped `grep -q` form was also wrong under `pipefail`), `--self-test` against a harness-produced fixture with 4 negative controls. [src: engineering-auditor pass 5, 2026-08-14 (K7)]

<a id="closed-next-k2-is-closed-2026-08-29-back"></a>

### **K2 is CLOSED (2026-08-29, backend-builder) — route-auth po

*kind: closed*

**K2 is CLOSED (2026-08-29, backend-builder) — route-auth posture gate landed after four audit passes asking for it (J7 -> K2 -> L3 -> M3); posture was already correct, no route changed.** Current measurement: gateway **89/84/5**, documents **64/60/4**, geometry **28 identity-free**. Floors kept at 88/64/28 DELIBERATELY (the count the gate must exceed, not a stale reading — one route has been added since Pass 7 M3 measured 88) plus an `unwalked` cross-check against each app's own OpenAPI schema. Walker uses `fastapi.routing.iter_route_contexts`, not hand-recursion — the latter gets the right count with wrong paths/dependencies on nested/include-level auth, a false-positive risk on a security gate documented in CLAUDE.md. 13 tests, controls proven (naive walk refused at `3 < 88` after passing the posture check alone). See Done archive / `docs/CHANGELOG.md` "K2 CLOSED" for full detail. [src: engineering-auditor pass 5, 2026-08-14 (K2); was J7, 2026-07-30]

<a id="closed-next-pbt-1"></a>

### PBT-1

*kind: closed*

**PBT-1 is CLOSED (2026-08-29, kernel-architect) — the randomised sweep that found SETTLE-2/3 is committed as a seeded fixed corpus** (2000 trials, `seed 20260822`, +10.3s/0.9% of the pytest job), and its alarming 7-of-155 violated-constraint headline is re-measured at 0-of-1328 (post SOLVE-CRASH-1). Argued against `hypothesis` (reproducibility from the commit alone, since only the orchestrator can read CI). Mutation-checked against both root causes it was built from. Three NEW findings reported rather than fixed — SOLVE-CRASH-1 (closed, above), SOLVE-CONFLICT-MOVED-1, and SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (both still open, below). See Done archive / `docs/CHANGELOG.md` "PBT-1 CLOSED" for the full argument. [src: docs/AUDIT-ENGINEERING.md "Pass 9" N2, filed by backlog-groomer pass 11]

<a id="closed-next-settle-bench-1"></a>

### SETTLE-BENCH-1

*kind: closed*

**SETTLE-BENCH-1 RENAMED/ELEVATED -> SETTLE-PERF-1 (P1->P0), groom pass 12.** Uncommitted engineering-audit Pass 10 turned the "documented n^3 worst case" into a live measurement (1,560x at 48 lines, 230s at 96 — DoS-shaped against the gateway's 90s no-cancel timeout). Full ticket moved to the Ready section, top of queue.

<a id="item-contract-1"></a>

### CONTRACT-1

*kind: item-story*

kind: defect (contract/documentation drift a client relies on). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 9" N3): SOLVE-1's `_dimension_readouts` now reports the MEASURED value whenever it disagrees with the requested one by more than `SATISFIED_TOL_MM`, but the pydantic docstring (`packages/py-kit/src/py_kit/schemas/ sketch.py:575-605`) and both committed OpenAPI docs still say `value_mm` is "the evaluated literal/expression value that was fed to the solver" — i.e. the opposite of what SOLVE-1 does in exactly the case it exists to handle, with no field distinguishing requested-vs- measured. FIX: correct the docstring in two sentences; consider an explicit `verified`/`measured: bool` field so the substitution is disclosed in the payload rather than inferred from a sibling (`status`) on a different object.

<a id="item-sec-test-1"></a>

### SEC-TEST-1

*kind: item-story*

kind: capability (test gap on a correct-today, refactor-fragile control). MEASURED (`docs/ AUDIT-ENGINEERING.md` "Pass 9" N6): `upstream.py:186-189` builds the forwarded header set explicitly rather than proxying, and the only caller adding a principal is `parts.py:88` — so a forged `X-Loft-Principal` cannot reach `documents` today, but this is correct BY CONSTRUCTION, one plausible refactor ("forward the client's other headers through") away from being wrong, with cross-tenant impersonation as the failure mode, and `grep -rn "spoof\|impersonat\|forged" services/gateway/tests` finds only JWT-forgery tests. FIX: two request-level tests — a client-supplied `X-Loft-Principal` is dropped/ignored, and the upstream header always equals the authenticated token's subject (the second half already exists in `test_assemblies_proxy.py:275`).

<a id="item-p2-s-k3-no-automated-licenc"></a>

### - [ ] (P2, S) **K3 — no automated licence gate over the ~1,0

*kind: item-story*

(`.github/workflows/ci.yml`, `scripts/`).

<a id="item-p2-s-k8-three-of-the-last-f"></a>

### - [ ] (P2, S) **K8 — three of the last five commits landed w

*kind: item-story*

(process). `d091112` (FB-20), `a2bb859` (CI-3), `0580f7d` (REV-1d) — reconciliation of a stopped agent's work is the right call per RETRO §1.2, but the debt needs to be VISIBLE where the groomer reads, not just in `git log`.

<a id="item-rev-2"></a>

### REV-2

*kind: item-story*

(`.github/workflows/e2e.yml:380`). Filed 2026-08-13; PROVEN BY EXECUTION in the review. `grep ... || true` absorbs grep's exit 2 (no such file) as well as exit 1 (no match), so renaming `apps/web/playwright.config.ts` to `.mts` — which Playwright still auto-discovers — with `retries: 2` injected prints `posture: no retries, --fail-on-flaky intact` and exits 0. The only trace is one swallowed stderr line. Exactly the "enumerated gate that quietly stops covering" shape the same file's prose condemns 200 lines above.

<a id="item-rev-5"></a>

### REV-5

*kind: item-story*

(`apps/web`). Filed 2026-08-13. (a) `requireRenders` — the strict mode `de3755f` shipped precisely to stop a census sampling a stale buffer — has ZERO product consumers. All three call sites are in `qa-harness.spec.ts`, the gate that tests it. Note the review's warning before wiring it in: `waitForRenders` counts renders since the WAIT starts, so `requireRenders: true` at a census site throws whenever the render already landed, which is the common case.

<a id="item-ci-4"></a>

### CI-4

*kind: item-story*

Downgraded P2->P3 this pass: every diagnosed cause is now closed (CI-5, CI-5a, QA-SEL6-ORTHO-1, the shard-4/4 hem spec, QA-CI4-HEADROOM-1) and the imbalance itself is fixed (CI-BAL, below, duration-aware sharding, verified on the real CI runner at 1.16x spread). **REMAINING under this umbrella: QA-CI4-MATE-1 alone** (a mate-axis reachability scan measured zero addressable pixels once under CPU load, in 1 of 6 runs — filed as its own ticket, unreproduced hypothesis, do not "fix" by re-running until green).

<a id="closed-next-ci-bal"></a>

### CI-BAL

*kind: closed*

**CI-BAL is CLOSED (2026-08-29, platform-builder) — the e2e shard split is duration-aware (`scripts/e2e-shard-plan.py`, `scripts/e2e-durations.json`, longest-processing-time packing over measured per-file duration), and the two cheaper alternatives (splitting the heavy spec files; more workers / `fullyParallel`) were ruled out by measurement, not taste.**

<a id="closed-next-ci-5"></a>

### CI-5

*kind: closed*

**CI-5 is CLOSED (`2874f0a`, 2026-08-28, orchestrator) — a red e2e shard's failure list was unreachable from the orchestrator's only channel (job-log tails of 60/190/255 lines all failed to reach it past service-log/upload chatter). Every run now ends with a compact verdict block naming each failure, guarded against silence (`::error::` + exit 3) and cross-checked against the report's own stats. See Done archive.**

<a id="closed-next-ci-5-2"></a>

### CI-5

*kind: closed*

**CI-5a is CLOSED (`ecc1fb7`, 2026-08-28, orchestrator) — the verdict block was miscounting a declared `test.fail()` case as a real failure (classified from `results[].status` instead of Playwright's reconciled `tests[].status`); its own cross-check is what caught it. The inversion (a declared-fail that PASSES) is now named too, as `XPASS … [annotation NO LONGER HOLDS]`. See Done archive.**

<a id="closed-next-ci-2"></a>

### CI-2

*kind: closed*

- [x] (P2, XS) **CI-2 — `deploy-path` never got the per-SHA concurrency fix, so it is still evicting runs** (`.github/workflows`). Filed 2026-08-08 by the orchestrator from the CI board. `ci.yml` and `e2e.yml` both key their PUSH concurrency group on `github.sha`; `deploy-path.yml:39-41` still reads `group: deploy-path-${{ github.ref }}` with `cancel-in-progress: false`, and its header comment justifies that with "Runs QUEUE instead, so one always completes." That reasoning is the exact one CLAUDE.md records as false: a group admits one RUNNING plus one PENDING run, and a newer arrival evicts the pending one no matter what `cancel-in-progress` says — which only governs runs already holding a runner. EVIDENCE: `207d36c` (run 31237861400) and `e53e4e4` (run 31237776502) both came back `cancelled` on `deploy-path` while their `ci` and `e2e` runs completed. `list_workflow_jobs` on 31237861400 returns `{"total_count": 0}` — no job ever started, which is the eviction signature, not the `timeout-minutes` one (a timeout kills ONE job near its ceiling and leaves siblings green). FIX: mirror `ci.yml`'s expression — per-SHA group on `push`, per-ref on `pull_request` — and correct the stale comment in the same commit so the next reader does not re-derive the wrong model. Cheap: deploy-path is the 86 s job, so per-commit runs cost little. ACCEPTANCE: two commits pushed back-to-back each get a completed `deploy-path` run; no `cancelled` with zero jobs. [src: orchestrator CI read, 2026-08-08] SHIPPED 2076de4. Recurred and was re-measured before the fix: `8d386ab` came back `cancelled` on deploy-path on 2026-08-14 while the six commits either side succeeded — **81 s wall clock (13:27:33 -> 13:28:54) and `total_jobs: 0`**, against a 45-minute ceiling. Zero jobs is the decisive discriminator: an eviction kills a PENDING run before any job exists, whereas a `timeout-minutes` kill requires a job to have started and reached its limit. So there is no second bug hiding behind the word "cancelled" here. The builder REFUSED to take the orchestrator's eviction diagnosis on trust — it cannot read CI — and recorded the observation in the workflow file with its evidentiary status ("the reason somebody looked, not the proof"), resting the change on the mechanism instead. The orchestrator then fetched the per-job breakdown above. That is the right shape and is worth copying. It also priced the trade honestly and found a SECOND cost the ticket did not name: ref-keying was *serialising* the image builds, so per-SHA means up to 8 concurrent deploy-path jobs under four pushing agents, on top of ci's 6 and e2e's 5. Judgement recorded in-file that the trade is still right — a serialised gate that discards evidence is not cheaper, it is unpaid — and that if runner contention bites, the lever is the TRIGGER (`paths-ignore`), never the key. GATE: `scripts/check-workflow-concurrency.py`, wired into `just lint` and ci.yml's `compose` job, stdlib-only, ~60 ms. It derives coverage from the filesystem (every workflow with a push trigger), so a workflow added tomorrow is covered and no list can go stale. Verified by the orchestrator against the REAL pre-fix file, not a fixture: `git checkout HEAD~1 -- .github/workflows/deploy-path.yml` makes it exit 1 naming `deploy-path-${{ github.ref }}`. `--self-test` carries 8 fixtures of which 5 MUST fail, including **arms swapped** (PR keyed on sha, push on ref) — the symmetric mistake a check that merely grepped for `github.sha` would sail past, which is this repo's own guard-encodes-the-direction-of-its-defect lesson applied in advance. It also cross-checks its own line reader against PyYAML and REFUSES to report on disagreement, with a negative control on the refusal itself. NOT verified: no image was built (registry 403), and the acceptance criterion above — two back-to-back pushes each completing — can only be observed on the next real double push.

<a id="item-fb-18"></a>

### FB-18

*kind: item-story*

Founder, 2026-08-01. Almost certainly the gateway's typed `upstream_timeout` (`py_kit/errors.py:134`) — which says the honest thing ("we gave up waiting") and is useless to the user, because the work may have been progressing fine. TWO questions, and they have different fixes, so MEASURE before building: (a) is a 50-instance pattern inherently that expensive (rebuild scales ~N^1.85 per docs/PERF.md, so it may legitimately be), or is the pattern RE-EVALUATING its source body per instance? If the latter the fix is caching and no queue is needed. (b) If it is genuinely long, a long compute must stop riding an HTTP request: move evaluation onto the arq/redis queue already on the roadmap so it becomes a JOB — submitted, progress-reported, cancellable, resumable — i.e. "47 of 50, 12 s left, cancel?" instead of a dead request.

<a id="item-flow-1"></a>

### FLOW-1

*kind: item-story*

Founder: "we need to fine tune the flow from drawing the sketch. Also, the main pages for selecting parts... Flow is critical for users. Think about it as you build. How should we direct the user? Hopefully in a way to leave fusion and go OS." Now a standing rule in CLAUDE.md's design mandate, so this item is the first concrete cash-out, not the whole of it. TWO surfaces. (a) SKETCH -> FEATURE: today you draw, then hunt. The solved sketch should OFFER its likely next action with the profile already selected; extrude wants a draggable arrow in the viewport with the numeric field as the precision fallback (we have the form and no handle, which is the biggest "not a modeling tool" gap we have); dimensions typed during the draw (FB-16); and no ambiguous exit (FB-13). (b) PARTS PAGE: benchmark Onshape's document list, NOT Fusion's data panel which is genuinely weak — recent-first, searchable, thumbnails that show STATE (solved / errored / stale), folders that do not read as a filesystem (WS2 folders already shipped, so this is presentation over an existing model). Acceptance: a named flow walked end to end with the CLICK and KEYSTROKE count before and after, at 1600 and 1280, against a Fusion/Onshape reference — a flow claim with no count is an opinion. Deliberately P0/L: every FB-1..FB-19 report was a flow failure rather than a missing capability, so this is the root the others are symptoms of.  UPDATE 2026-08-14: sliced. The sketch->feature half is now three concrete Ready items — SKETCH-1 (sketch re-open), PICK-1 (pick-stamped- with-tip root cause), VP-1 (orbit while sketching) — plus DRAG-1 below (hover-normal arrow, a direction control, NOT yet the full draggable- distance handle M5 asks for — that remains open). Fresh audit confirmation (product-auditor pass 2026-08-14): M4 measures the "no proposal after a solved sketch" and "camera stays normal-on through the extrude preview" halves precisely; M5 re-confirms zero manipulator DOM exists anywhere (fillet/shell/hole depth too, not just extrude); M18 finds no orthographic mode and a ViewCube that does not snap to the face clicked.

<a id="item-qa3-2"></a>

### QA3-2

*kind: item-story*

(frontend + geometry). Two things compound: `faces._face_plane` puts the datum origin at the face's AREA centroid (not the part origin, not any feature of the part), and `sketch/snap.ts` snaps only to the sketch's own entities and the grid — never a body edge, a hole centre, or projected geometry — with no way to dimension to imported geometry. Measured consequence: a register ring drawn at sketch (0,0) on a vendor plate's back face came out **0.065111070 mm** eccentric to the shaft bore, exactly the centroid shift a previously-added Ø3 hole caused (`15.5·π·1.5²/(1739.29−15.76π−π·1.5²)`, agreeing to 9 decimals) — a scrap part with every number on screen correct. Acceptance: projected/reference geometry from the body into the sketch (at minimum circular-edge centres + straight edges of the sketched face), snappable and dimensionable; and the sketch frame's origin drawn and named against the part.

<a id="item-sel-1"></a>

### SEL-1

*kind: item-story*

(`apps/web`). `ModelMesh.tsx`'s pointer handler already resolves the exact face ordinal under the cursor (`faceOrdinalOf`) and throws it away; extend to `onPointerMove`, route the hovered ordinal through the SAME localized-highlight machinery "feature selected" already uses (`setFaceMaterials` + `subsetEdges`), and reuse existing `viewport.facePick.hover`/`viewport.hover` tokens — zero new palette. Graceful fallback to today's whole-body glow when the mesh can't be face-partitioned. Also fixes armed face/edge picks (datum, hole, shell, draft, sketch-on-face, fillet, chamfer): the raycast becomes the PRIMARY hit-test (click anywhere on the face/edge), demoting `PickNode`'s fixed 24px centroid/midpoint button to a keyboard/touch fallback. Design + acceptance A1/A2/A7: `docs/design/pre-selection.md` §1, §6.  **A1 SHIPPED 2026-08-05 — the pointer now addresses a FACE.** Hover resolves the ordinal under the cursor and routes it to its own draw group (`setFaceMaterials` slot 4) with its boundary traced by `subsetEdges`; the whole-body glow survives as the fallback for a mesh that cannot be face-partitioned, or a single-face body. Gated by `e2e/face-hover.spec .ts` (5 specs), mutation-verified: deleting `onPointerMove` turns "the addressed face FOLLOWS the cursor" red (distinct ordinals seen across a grid sweep 2+ -> 1) while the arrival case stays green — r3f re-fires `onPointerOver` only on mesh ENTRY, never between faces of one fused mesh, which is the whole defect. Two deviations from the spec, both forced by the founder capture rather than by taste: the surface tint is a NEW token (`facePick.hoverTint` #EFD6AE) because the reused `hoverSurfaceTint` is ~5 % off white — invisible once localized to one face, i.e. a cue that does not cue; and the traced boundary draws `depthTest:false`, because its segments are numerically identical to the body-wide edge overlay's and the two came out STIPPLED. A2 (raycast as the primary hit-test for armed picks — the 9.9 %-vs-50 % reachability floor) and A7 remain OPEN; this ships the hover cue, not the hit-test. **A2 SHIPPED 2026-08-05 — the drawn face IS the target: 9.9 % -> 84.6 %.** `ModelMesh` publishes its geometry through `partView`; `FacePickOverlay` raycasts it and resolves the struck triangle to a B-rep ordinal, which is already `OverlayFace.index`, so there is no mapping table to drift. All three armed-pick call sites (sketch-on-face, datum, hole) get it for free. `PickNode` is unchanged and demoted to what §5 asks: keyboard focus, screen-reader name, touch target. A hit on a NON-pickable (non-planar) face is ignored rather than snapped to a neighbour. Both FB-3/FB-5 `test.fail`s in `founder-picking.spec.ts` flipped to real assertions — and BOTH needed their measurement repaired first, which is the reusable lesson: the affordance case hit-tested the DOM, and `elementFromPoint` answers "the canvas" for a raycast handler, so it would have stayed at 9.9 % with the defect fully fixed; the seat case clicked a hardcoded coordinate that is 40 px OFF the body, so it had never once failed for the reason it claimed. **A7 SHIPPED 2026-08-05 — the reticles stop out-shouting the model.** `PickNode`'s mark rests dimmed and returns to full on hover, focus-visible and selected; the 24 px hit area (WCAG 2.5.8) is untouched, because trading "too many to see" for "cannot hit it" would be the worse defect. It follows A2: once the drawn surface is the primary hit-test, these marks are the keyboard/touch fallback rather than how you aim. NOTE the acceptance asked for a pixel census and it is not deliverable — every census in `e2e/support.ts` reads the WebGL canvas, and a `PickNode` is a drei `Html` DOM node that puts ZERO pixels on it. That blindness is itself the finding: it is why the "DOM-square blanket" survived every pixel gate we own. Gated instead on the property that decides it (`PickNode.test.tsx`), which is exact and cannot be satisfied by degrading anything else. Shots at 1600 AND 1280 under `docs/screenshots/sel1-pick-reticles-*`.

<a id="item-drag-1"></a>

### DRAG-1

*kind: item-story*

(`apps/web`, `packages/design`). A single brass arrow along the addressed face's normal (planar: `signature.normal`, already computed; curved: the raycast-hit triangle normal) on hover; while Extrude/Cut is armed it becomes a forward/reverse PAIR wired to the editor's existing `direction` field, so the viewport — not a text toggle nobody checks while aiming — shows which side removes material. World-space length clamped to the face's own footprint (mirrors `FacePatch`'s disc-radius formula). New token group `viewport.faceNormal` — see `docs/design/pre-selection.md` §4 for the exact fields.

<a id="item-conc-8"></a>

### CONC-8

*kind: item-story*

(kernel). Found while building the load harness, not looked for: on the `housing_tree(50)` tray, bumping the last `distance_mm` by 0.01 mm makes the picked-edge fillet that consumes that extrude fail to resolve its edge signature, so a valid part becomes a failed tree from a change no user would consider structural. This is the known stage-1 topological-naming limitation showing its edge, but the trigger is small enough to be worth a regression case and a better error message. [docs/PERF.md 2026-08-01]

Restocked 2026-07-23 (HEAD `0ed9f74`) — the overnight batch converged 18 Ready items (WF-1/PB-1 width extents, drawings dead-capability drain D1-D4, MB-4c wire+frontend, e2e hardening) — all archived below (Done, one line each).

<a id="item-p2-m-drawings-parity-4-assem"></a>

### - [ ] (P2, M) Drawings parity #4 — assembly drawing views + 

*kind: item-story*

: compose routes branch on `request.assembly` → `evaluate_assembly_drawing_views` → mapped into the `EvaluateDrawingViewsResult` `place_sheet` consumes (`assembly_error`→`part_error`, dimensions empty — assembly-view dims out of v1). Assembly views now compose REAL silhouettes (visible + hidden-dashed) END-TO-END at the API; part compose (`assembly=None`) byte-identical; 6 new compose gates green; DE-4 cache key already hashes the whole request. (Reconciled by the orchestrator after the builder was killed by the session usage limit mid-regression-run — work re-verified green: drawings regression suites 100%, format + contracts regen completed, gen-check + web typecheck clean.) - [x] (b1) **BOM data model — SHIPPED 2026-07-25** (backend-builder): `GET /drawings/{id}/bom[?sheet=]` (documents read model + gateway proxy, `DrawingBomLine`/`DrawingBomResponse` extending the shipped `BomLine`). **Item numbers are DERIVED, never stored** (design §8a.1): numbered by first appearance in the assembly's `order_index`, so a part RENAME can never renumber a print (the name-sorted `/assemblies/{id}/bom` order is deliberately different, gated). Staleness is visible not silent — `assembly_version` echoed (tip-tracking, §8a.2) — and every failure is typed: `drawing_bom_source_not_assembly` / `sheet_has_no_views` / `drawing_bom_source_missing` 422, `sheet_not_found` 404, a dangling reference keeping its number + quantity with `missing: true`. 15 documents regressions x2 dialects + 4 gateway proxy gates; contracts + ts-client regenerated. - [x] (c1) **web — the setup band drafts an ASSEMBLY — SHIPPED 2026-08-27** (frontend-builder, REACH-ASMDRAW): `drawing-part-select` widened from a part picker to a grouped SOURCE picker over parts AND assemblies (`drawing/source.ts`; `SelectField` learned `optgroup`), testid kept so the twenty existing drawings specs stay green. `AssemblyPage` gains the band `Drawing` action → creates the drawing and opens it at `?source=<assembly>`, pre-selected. Compose gates on the source KIND (an assembly sheet has no client feature tree and needs none); flat pattern + section disable with the reason, keyboard path guarded. The Views panel now counts PLACED edges when there is no client evaluate — it read "0 edges" over a full assembly sheet. E2e `assembly-drawing.spec.ts` (real HLR ink asserted, 1280 band fit). Deferred: assembly fit-scale (needs the solved compound's extents). - [x] (c2) **web — the sheet's numbered PARTS LIST — SHIPPED 2026-08-27** (frontend-builder, REACH-ASMDRAW): `GET /drawings/{id}/bom` gets its first caller in 13 months of existing (`fetchDrawingBom`). A Parts list block sits beside Notes: balloon item numbers (a circled numeral — the drafting artifact, and the number is content, not decoration), qty, current names, each row opening the document it names; a `missing: true` line keeps its number and reads "Deleted document". On a PART-sourced sheet the block is PRESENT but disabled, carrying `drawing_bom_source_not_assembly` as a readable sentence that is FOCUSABLE — reachable by Tab, not hover-only. E2e `drawing-parts-list.spec.ts` (item 1 qty 2 / item 2 qty 1 by name, numbers survive a reload, row navigates, reason read via Tab). `check-ui-parity.py` UNCALLED OPERATIONS 3 -> 2 (82/85 -> 83/85). - [ ] NEXT SLICES (scoped): (b2) **BALLOONS — one whole slice, kernel + backend + web together** (splitting it would persist balloons no serializer draws = a dead capability). Decisions already made in drawings.md §8a.3: a balloon stores the BOM line KEY (`ref_document_id`+kind) + its authored 2D leader/anchor and NEVER the number (resolved from (b1) at compose time); a balloon whose document is no longer instanced is a typed `balloon_item_missing` dangling marker, never a stale number. Work: promote the `Annotation` alias to a `type`-discriminated union with a `balloon` member (documents persists it through the SHIPPED annotation table — no migration); add `ComposedBomTable` + `ComposedBalloon` to `ComposedSheet` and place them in geometry `place_sheet` (thread the resolved BOM through `ComposeDrawingRequest`, additive/null = today's byte-identical sheet); all three serializers render them; web authors the balloon + renders the table.

<a id="item-cosmetic"></a>

### COSMETIC

*kind: item-story*

(decision + trade-off + modelled-thread upgrade path in `geometry/kernel/threads.py`): the kernel cuts the ISO tap-drill bore `D - P` and carries a typed designation for drawing/BOM callouts — no helix, so a tapped hole costs 1 face, not hundreds. `thread: IsoMetricThread | None` is its OWN optional param, NOT a 4th `HoleType` member (threading is orthogonal to the recess → a counterbored tapped hole is one feature, and the `HoleType` union stays untouched). ISO 261 table M1.6–M64 (coarse + fine); `hole_thread_unsupported` (unknown designation) / `hole_thread_mismatch` (bore outside `[minor, nominal)`) are validated BEFORE any geometry, so neither degrades to a plain hole wearing an uncuttable callout. Proof: golden `hole-tapped-m10x1.5-40x25x10` (analytic 9432.549826945344 = 10000 − 180.625π; topology 7/15/1 — IDENTICAL to the untapped bore), the evaluate response is BYTE-identical to the same hole untapped, and matrix verb `hole_tapped` (+8 cells) proves pattern/mirror of a tapped hole array the BORE. gen-check clean (additive optional field). - [x] Web authoring (2026-07-25, frontend-builder). A `Tapped` CHECKBOX beside the Type control (not a 4th segment — threading is orthogonal to the recess) reveals a drafting thread note: brass callout stamp, ISO size + pitch pickers (coarse first), tap-drill preset chip. Picking a designation DERIVES `diameter_mm` to `D - P` without locking it (a shop's 6.8 for M8x1.25 still submits); both typed errors are guarded client-side and humanised via `friendlyFeatureError`. ISO 261 table mirrored in `features/thread.ts`, kept honest by a test that parses `geometry/kernel/threads.py`. The FEATURE TREE row carries the designation (`hole · M10x1.5`) — a tapped hole's solid is byte-identical to its bore, so the UI is the only place it exists. e2e (derive → mismatch guard → Solved → survives reload; + a tapped counterbore) + founder shots at 1440/1280. [done 2026-07-25] - [x] Drawing THREAD SCHEDULE (2026-07-31, kernel-architect) — BACKLOG #50, the output half. A tapped hole's solid is byte-identical to its bore, so the print is the only place the thread can exist; it reached none. Now a derived QTY / THREAD / TAP DRILL block (bottom-left, the corner the title block and bend table leave free) in SVG, PDF and DXF, rolled up per designation from the feature params at compose time — never stored, so a re-tapped hole cannot leave a stale callout. Asserted on the DOWNLOADED bytes incl. a route-level POST.

<a id="item-mb-hole"></a>

### MB-HOLE

*kind: item-story*

(`services/geometry`, `apps/web`). Found 2026-08-11 by qa-tester while verifying SEL-7 on the two-body `seedBoredPlateAndBlock` fixture; NOT a SEL-7 regression — measured with the body drawn and hidden, identical either way. MEASURED, three runs, same face each time (`plane-pick-face-4`, the plate's top at OCCT 30, 30, 10): one-body dense plate -> **Solved**, volume 34 020.8 -> 33 738.05 mm³ (Δ 282.7 = Ø6 x 10); the SAME plate as body 1 of a two-body part -> **Failed / HOLE_OFF_BODY**, volume unchanged at 38 020.8; the second body's own top face -> **Solved**, 38 020.8 -> 37 738.05. The plate's BOTTOM face fails too, so it is the BODY that is unreachable, not a face-normal case. Mechanism (read-only): `evaluate.py:_hole` drills `state.active_body`, and a `merge: false` extrude makes the NEW body active — every modifying feature inherits this, so Fillet/Chamfer/Shell on an earlier body are very likely the same defect and should be measured in the same pass. FLOW: the pick offers a target the command cannot act on, and the refusal arrives only AFTER Create, as a red tree row ("no dead ends, no ambiguous exits"). FIX candidates: derive the target body from the picked FACE rather than from `active_body_id`, or withhold the faces of non-active bodies in the pick (worse — it makes the model invisible instead of wrong).

<a id="closed-next-qa3-3"></a>

### QA3-3

*kind: closed*

- [x] (P2, M) **QA3-3 — selecting a Ø3 hole lit the whole plate; a feature now owns the faces whose SURFACE it created. CLOSED 2026-08-01** (kernel-architect). `attribute_faces` credited a face to the earliest feature after which it existed in its FINAL form, so any cut re-bounding a large face took it: the remix's 5th hole owned 3 of 18 — its 75.4 mm² wall plus the vendor plate's 1 323.8 mm² top and 1 682.7 mm² back. The rule is now geometric, not a size heuristic (an area cutoff would fit this plate and invert on the first small face drilled — gated by a 3×3×20 post whose 5.9 mm² drilled top is smaller than the 125.7 mm² wall of the same bore): each face resolves to the earliest snapshot that already had its supporting `SurfaceKey` — canonical plane / cylinder / cone / sphere / torus read off the exact B-rep — provided the final patch lies INSIDE that surface's extent then, since a plane is unbounded and two disjoint coplanar cubes would otherwise merge (6/6 → 10/2 on `multibody-two-disjoint-boxes` before the guard). NEMA remix now **1/17 of 18** (hole owns only its bore wall); block+hole 1/6 of 7; chamfer-plate 4/6 not 10/0; shell-pinch 8+17 not 17+19; 28 of 47 feature-tree goldens change ownership, none change stored numbers (attribution is not a golden field). No contract change — a face still carries one `feature_id`. Cost: the surface key + extent add ~13.5 µs/face and the index is built by the RECORDER, so the interactive pass stays O(final faces) at 14/23/46 ms (tray N=25/50/100, was 13/21/39 by PERF-5b) and recording goes 21/56/155 → 27/71/203 ms. New `test_provenance_surface.py` (11 gates, incl. monotonicity and free-form fallback). `import-remix.spec.ts` exact counts need 3→1 / 15→17 and 6→5 / 5→6 (frontend territory; handed over, not edited here). [docs/QA-REVIEW.md 2026-08-01 QA3-3]

<a id="closed-next-gate-1"></a>

### GATE-1

*kind: closed*

- [x] (P2, S) **GATE-1 — CI ran nothing that drove a browser, so a stale spec could sit red at HEAD for a day while every commit read green. CLOSED 2026-08-01** (platform-builder). `.github/workflows/e2e.yml` runs the FULL Playwright suite on every push that touches code, sharded 4 ways (`scripts/e2e.sh --web-only -- --shard=i/4`; `just e2e-web` reproduces a red shard locally). The choice was argued from cost and coverage, not preferred: **PR-only** would never have run (we push straight to `claude/**` and open no PRs); **nightly-only** attributes a failure to ~20 commits up to 24 h later, which IS the defect being closed; a **write-path subset** is a hand-maintained list — the "enumerated gate quietly stops covering" class this repo has now hit four times — and would not have caught this bug either, since `interaction-depth.spec.ts` is a right-click/ghost-preview spec no honest subset would list. Sharding is derived from the FILESYSTEM, so a spec added tomorrow is gated the day it lands. Wall clock ~8-15 min per push (352 tests / 81 files; ~30 min serial quiet, ~60 min under four-agent load), i.e. at or under ci.yml's `python` job, so feedback latency does not regress; ~45-75 runner-min per code push. A `reconcile` job re-derives the expected set with `playwright test --list` and fails unless the shards executed it exactly once between them (`scripts/e2e-shard-audit.py`, proven against three negative controls: a spec no shard ran, a spec two shards ran, a missing shard report). **NOT covered per push, named so nobody assumes otherwise:** markdown-only commits (30 % of the last 100 — `paths-ignore`, so no e2e run exists for that SHA at all; `git show --name-only` distinguishes it from an eviction), the browser against Postgres (this gate uses the native SQLite boot — `deploy-path.yml` drives the real Postgres/MinIO round-trip per push), and non-Chromium browsers (the config declares only Chromium). One disclosed compromise: the gate runs `--retries=1`, because the measurement found a racy spec (GATE-1a) and a gate people learn to re-run is worse than no gate — a deterministic defect still fails both attempts, and a retried test is NAMED as a warning every run rather than swallowed. Acceptance met by deliberate failure, not assertion: the exact stale assertion from `60a9553` was re-introduced, pushed, and CI rejected it — run ids in the batch report, with `ci.yml` GREEN on the same commit, which is the whole point. **The first attempt at that proof FAILED, and the failure is the useful part.** All three pushed runs came back red — including the two that should have been green — because Vite never answered inside the 60 s `webServer.timeout`: Vite forces `dns.setDefaultResultOrder("verbatim")`, so on a DUAL-STACK host its default `localhost` binds `::1` while `baseURL` asks for `127.0.0.1`; the process stays alive and never answers ("Timed out", not "exited early"). Unreproducible here — the dev container has no IPv6 loopback at all, which is exactly why it survived every local run. The red negative-control commit was therefore red for the WRONG reason and proved nothing, which is the same defect this repo keeps closing: a gate asserting something it does not know. Fixed by binding the literal IPv4 loopback (`pnpm dev --host 127.0.0.1`), piping the webServer's output so a failure names its cause instead of timing out silently, and a CI preflight in `scripts/e2e.sh` that serves the app on an isolated port and PRINTS which address answered — so if the diagnosis is ever wrong again, the log says so in one line rather than costing a round trip. [src: batch-end e2e 2026-08-01]

<a id="closed-next-gate-1-2"></a>

### GATE-1

*kind: closed*

- [x] (P2, XS) **GATE-1a — the browser gate no longer needs `--retries=1`. SHIPPED 2026-08-01** (frontend-builder). `--retries=1` is out of `.github/workflows/e2e.yml` and `--fail-on-flaky` is passed to the reconcile audit, so a retried pass is a red build again. The fix is the rig's own signal rather than the suggested poll-the-width (which would have retried the assertion but still guessed at the settle): the spec blanks `data-fit-rect` and waits for `CameraRig`'s `onSettle` to write a fresh one, so it returns as soon as the move lands and cannot pass early. Measured both ways under four CPU burners on 4 cores (load avg ~8): the OLD shape failed **1/10** repeats, the new one passed **10/10** in the same window — the negative control matters, since "10/10 under load" is worthless if the load was too light to expose the race. Suite audit: 17 `waitForTimeout`s, 4 gating a non-retrying assertion — `viewport-gestures`' raster compare is now an `expect.poll`; `part-visibility` / `assembly-visibility` sample after real PAINTS (`support.ts waitForFrames`, rAF ticks, which stop when the browser stops drawing) instead of 400/450 ms of wall clock. The other 13 are screenshot settles or absence assertions, where a sleep is correct; `viewport-makeover:373` is named explicitly — it sleeps to prove the camera did NOT move, so a slow box can only make it pass, never fail. 30 specs re-run green under the same load. Residual, filed rather than hidden: the `--fail-on-flaky` help text in `scripts/e2e-shard-audit.py` still says the flag is "off while the known racy specs are being hardened" (platform territory, one line). The shape this closes, for whoever hits it next: a fixed sleep is only ever safe before a LOCATOR assertion, which retries itself; before a numeric one it IS the gate, and it has to be right every time on a machine you do not control. [src: GATE-1 full-suite measurement 2026-08-01]

<a id="closed-next-perf-1"></a>

### PERF-1

*kind: closed*

- [x] (P2, S) **PERF-1c — the prefetch headline is the BEST case, and we do not know the typical one** (kernel + QA). PERF-1b's table is measured with the warm run to COMPLETION: the 7.0x commit / 7.9x pick at N=200 `#192` assume the user sat in the editor for the full 28.9 CPU s the warm costs. A real edit is "open extrude, type 12, Enter" — 3-5 s. Since warming follows the same `N^1.85` curve, a few seconds of dwell reaches only a short prefix and removes a correspondingly small share of the rebuild (rough estimate, NOT measured: ~5 s of dwell at N=200 removes on the order of 15 %, i.e. 34 s -> ~28 s, not -> 4.8 s). Nothing is wasted — a partial prefix is a legitimate resume point and the work is the commit's own, moved earlier — but the number we publish should be the one a user gets. Acceptance: measure warm-completion-vs-dwell at 2 s / 5 s / 15 s for N=50 / 100 / 200, publish the EXPECTED win beside the ceiling in `docs/PERF.md`, and state which part sizes benefit at realistic dwell. Then decide, with the data, whether the trigger should fire EARLIER than editor-open — e.g. on feature-row selection, which precedes the dialog by a beat — and whether the 30 s budget is still the right split once the commit lineage is known to be the only one most dwells can reach. Founder question that prompted this: "is this the numbers users are experiencing or just what happens under the hood without them noticing?" — a fair challenge to a table that answered a different question than it appeared to. [src: founder 2026-08-01 · docs/PERF.md 2026-08-01] **ANSWERED 2026-08-01** (kernel): the win is a STEP at the warm's own completion (~0.85x the cold rebuild per lineage), not a ramp, because a partial prefix cannot help a request that already probed the cache. Expected commit win by dwell — N=50: 1.0x / **7.0x** / 7.5x at 2 / 5 / 15 s; N=100: 1.0x / 1.0x / **16x**; N=200: 1.0x at every dwell a human produces (its ceiling of 18.8x needs D >= 30 s). So the prefetch is worth 7x on a 50-feature part at a realistic 3-5 s edit and NOTHING at 200. The trigger did not move: it already fires on feature-row selection (the same event that opens the editor), and the deficit at N>=100 is seconds-to-tens-of- seconds, which no trigger nudge closes. No dwell timer either — the pessimisation was contention, not earliness, and a start delay would push the step further out. [docs/PERF.md 2026-08-01b]

<a id="item-perf-6"></a>

### PERF-6

*kind: item-story*

(kernel + frontend). BLOCKED ON PERF-1: with no cache, prefetching does the same 27 s of work twice with nowhere to put the result; with the cache it degenerates into warming it at the right moment, which is a small feature rather than a system. Two triggers earn their keep, and only two: (a) opening a feature editor is a genuine declaration that the prefix below it is stable for as long as the dialog is open, so warm 1..N-1 and let the commit cost one feature's work; (b) dragging the timeline rollback marker is a walk through prefixes that are already cache keys, so warm the neighbours of the current stop. Register/document hover prefetch is standard TanStack Query and worth nothing against these numbers — do not bother. TWO CONSTRAINTS, both non-negotiable. **A speculative body must never be publishable**: if a warm result is ever served for a tree it does not exactly correspond to, that is the silent-wrong-geometry class this repo has closed four times, so warming must be a distinct entry point from evaluate.

<a id="closed-next-x-p2-s-fit-model-frames-the"></a>

### - [x] (P2, S) **"Fit model" frames the CANVAS, not the VISIB

*kind: closed*

- [x] (P2, S) **"Fit model" frames the CANVAS, not the VISIBLE viewport — a big part is clipped by its own panels. FIXED 2026-07-31** (frontend-builder). `viewport/fitFraming.ts` measures the live DOM (every docked element carries `data-viewport-chrome`, plus the in-canvas reference cube, which has no rect of its own), charges each obstruction to the ONE edge that leaves the largest free AREA, and the rig frames into that rect and slides the orbit target so the part sits in its middle. A panel that collapses announces itself and the fit re-runs — but only while the modeler has not taken the camera by hand since, because yanking someone off a detail they zoomed into would be a worse defect than the one being fixed. The fit DISTANCE is now solved from the subject's projected corners under the real perspective (depth included: the near end of a long part projects wider — an orthographic first cut measured 51px of overhang on a 260mm rail), replacing the fixed 1.75x-diagonal rule that was blind to both the frame and the aspect ratio. `view-fit.spec.ts` fits three aspect ratios and asserts the body's projected bbox — read from canvas PIXELS, not from the same arithmetic — lies inside the rect on all four sides; mutation-verified (framing the canvas instead fails 4 of 5). Shots `viewfit-{before,after}-{1440,1366}.png`. [src: founder capture 2026-07-31]

<a id="closed-next-x-p3-xs-the-viewcube-is-clip"></a>

### - [x] (P3, XS) **The ViewCube is clipped by the window edge 

*kind: closed*

- [x] (P3, XS) **The ViewCube is clipped by the window edge and the timeline strip. FIXED 2026-07-31** (frontend-builder). The inset was 64px against a cube whose ISOMETRIC silhouette is ~√3 wider than its face, so its lower corner and the FRONT/RIGHT labels sat hard on the frame edge; it is now 96px, which also puts it on the same 12px gutter the ViewBar and the panels use. Its footprint is registered as a fit obstruction in the same pass, so a part can no longer be framed underneath it either. [src: founder capture 2026-07-31]

<a id="closed-next-x-p2-s-promote-the-durable-e"></a>

### - [x] (P2, S) **Promote the durable EDGE tier into `geometry

*kind: closed*

- [x] (P2, S) **Promote the durable EDGE tier into `geometry.kernel.edges`.** DONE 2026-08-24 (`c2700ee`, folded into NAME-2's closure): `resolve_edge_durable()` now lives in `geometry.kernel.edges`; fillet/chamfer and sheet-metal edge flange/hem pick it up via `select_edges`/`_fold_flange_off_edge`. [src: topological-naming §11]

<a id="closed-next-x-p2-s-frontend-half-of-n1-n"></a>

### - [x] (P2, S) **Frontend half of N1/N2 — say it on screen, n

*kind: closed*

- [x] (P2, S) **Frontend half of N1/N2 — say it on screen, not only on the print** (frontend). DONE 2026-08-01: the sheet already stamped the composer's words beside a broken marker (`6cc89b1`); this adds the two surfaces that were still missing and the panel tier that dropped both. `ComposedSheet.layout_issues` now raises a **sheet check strip** above the paper (composer's own sentences, per-row Auto-place that resets exactly the hand-placed views of the pair, an advice line where no reset would help) AND stamps the same `drawing-layout-issue` banner on the DOM sheet the three serializers use, so the client SVG export carries it too. `anchor.tier == "durable"` stamps a dashed RE-ANCHORED badge with one-click **Confirm** (append-then-delete; `drawing/anchorHeal.ts`), and an unresolved dimension's typed reason reads in the panel. Gate: `e2e/drawing-reanchor.spec.ts` resizes a dimensioned part 100 -> 120 and reads `120.000` in-app, then confirms the reference. [src: AUDIT-PRODUCT 2026-07-30 N1/N2]

<a id="item-geom-4"></a>

### GEOM-4

*kind: item-story*

`outer·C_outer = stored·C_stored + removed·C_removed` implies this directly, but `enclosing_face_match` only tests containment. MEASURED accepting a bogus signature: a plain 100x40 face with `area_mm2 = 4000` (== outer) and `centroid = (5, 3, 10)` returns `enclosing_face_match == True`. Would NOT have caught GEOM-3's vented-plate case (boss and plate share a centroid there), and no shipped test currently depends on it — a strengthening opportunity, not a live defect. FIX: when `stored == outer` (within tolerance), assert `centroid == outer_centroid` as an additional necessary condition before accepting the match.

<a id="item-qa-ci4-mate-1"></a>

### QA-CI4-MATE-1

*kind: item-story*

kind: defect (e2e, possibly app). Found by the CI-4 QA pass (2026-08-29, `docs/QA-REVIEW.md`) while reproducing shard 3/4: `pick-affordance.spec.ts:1680` ("assembly mates: each INSTANCE's own geometry is the mate target") failed in 1 of 6 full shard runs, only under two CPU spinners, with `mate axes addressable >= 40px along: #13 0px #14 28px` — axis #13 not SHORT but ABSENT, while its sibling #14 measured 28 px. 0 of 5 other runs. The leading hypothesis is that the overlay or the camera had not settled when the reachability scan ran, which is the same family as the two defects the pass DID close, but it is a hypothesis and is filed as such rather than patched. FIX: instrument first — record the mate-axis overlay's own settle state and the camera pose at scan time, reproduce under load, and only then decide whether the scan or the app is at fault.

<a id="closed-next-qa-ci4-headroom-1"></a>

### QA-CI4-HEADROOM-1

*kind: closed*

- [x] (P2, S) **QA-CI4-HEADROOM-1 CLOSED — both tests were ALREADY failing, the work was cut before the ceiling was raised, and my first theory about the cost was wrong.** kind: defect (e2e). Filed and closed by the CI-4 QA pass (2026-08-29); full write-up in `docs/QA-REVIEW.md`. The in-shard headroom table understated it: run ALONE, `qa-sketch-frame:478` timed out in 1 of 3 QUIET isolated runs and 3 of 3 under two CPU spinners, and `qa-sel4-verify:503` failed 3 of 3 under load — every one as a bare "Test timeout of 60000ms exceeded" naming none of the 54 clicks it might have died in. NOT the `expectSeatsSettled` mechanism (a fixed frame count whose wall time scales), and NOT the one I guessed either: I found the ring scan doing 1068 full-frame canvas readbacks, batched them 356:1, and the wall clock did not move. Phase timers then showed the truth — the ZOOM LOOP was 47 % of the test (15.8 s of 33.2 s) and the scan I had optimised was 0.6 % (190 ms), because the loop re-parked the pointer with a `mouse.move` before each of 48 wheel notches when the cursor was already there. FIXED in this order: work cut (one park per leg; one readback per scan; `qa-sel4-verify:382`'s hand-rolled 8 px halo now calls `clearOfSilhouette` — its second real use), then ceilings raised to 180 s from the measured distribution. After: `:478` 36.6-39.0 s quiet (4/4) and 49.7-57.5 s loaded (7/7); `:503` 52.1-53.8 s quiet (4/4) and **66 s** loaded (3/3) — a 10 % overshoot of the old 60 s, which is why it could never pass under load. Its 504 sequential pointer moves cannot be batched: the browser must hit-test each position and the hit test IS the measurement. No assertion weakened. Verified on a full shard 3/4 under two spinners: 171/171 expected, 0 unexpected, `load1` median 10.31 on 4 cores (~2.6x oversubscription, heavier than the 1.5x this ticket's acceptance named). **THE ACCEPTANCE CRITERION AS WRITTEN IS NOT MET, and this is closed on the two tests it NAMED, not on that.** "No shard-3/4 test under 3x its ceiling at 1.5x oversubscription" was over-broad for a ticket about two specs: the two are now 3.1-3.6x and 2.7x, but `pick-affordance:911`, `qa-reach-batch:298` and `qa-sel4-verify:382` were ~2.0x before this pass and still are, and at 2.6x load the worst is `pick-affordance:926` at 1.4x. A shard-wide floor is a larger piece of work — most of the remainder are census tests whose cost IS their assertion — and it wants its own ticket rather than being smuggled in here. Filed as QA-CI4-HEADROOM-2 below. One side-finding worth keeping: batching the scan removed an ACCIDENTAL settle (356 sequential awaits were letting the canvas repaint after a DOM-only wait), which failed once as "the origin ring must be visible ink"; fixed by stating the wait with `waitForFrames` rather than by un-batching. RESIDUE, not re-filed as a defect: `:478` is 49.7-57.5 s of REAL work under load, so a runner 3x slower than this box approaches 180 s again. The durable fix is fewer zoom legs or fewer notches, and both weaken a claim the test exists to make — a product-QA trade for the spec's owner, not a timeout tweak. [src: qa-tester CI-4 pass, 2026-08-29]

<a id="item-qa-ci4-headroom-2"></a>

### QA-CI4-HEADROOM-2

*kind: item-story*

kind: defect (e2e). Split out of QA-CI4-HEADROOM-1 (2026-08-29) rather than left as an unmet acceptance line on a closed ticket. That ticket named two tests and fixed them; the blanket floor it also asked for — no shard-3/4 test under 3x its ceiling at 1.5x CPU oversubscription — is NOT met and was over-broad for its scope. Measured at 1.5x: `pick-affordance:911` 2.0x, `qa-sel4-verify:382` 2.0x, `qa-reach-batch:298` 2.1x. At 2.6x oversubscription the worst is `pick-affordance:926` at 1.4x (43.3 s against the default 60 s). These are mostly CENSUS tests whose cost IS their assertion — hundreds of sequential pointer moves the browser must hit-test one at a time — so the readback batching that helped elsewhere does not apply, and the honest lever per test is either fewer sample points (weakens the claim, needs an owner's call) or a ceiling set from a measured distribution. FIX: work one test at a time, cutting redundant round trips first and raising the ceiling second, with the numbers written beside each — the pattern in `qa-sketch-frame:478`. DO NOT do a blanket sweep of `test.setTimeout` values: a ceiling nobody measured is what produced this ticket.

<a id="item-datum-deadcode-1"></a>

### DATUM-DEADCODE-1

*kind: item-story*

kind: cleanup (dead code). `17763b5` (groom pass 27) moved `OffsetPlanePanel` onto `datumSubmitBlocker` directly; `canSubmitOffset` is now referenced only from `datum.test.ts`.

<a id="item-shortcut-sheet-sketch-fit-1"></a>

### SHORTCUT-SHEET-SKETCH-FIT-1

*kind: item-story*

kind: defect (docs-in-product accuracy). `registry.ts`'s View group note reads "Whenever the camera is yours (not while sketching)" — false since `f9fcce6` (F-11), which binds the SAME `0` key (`FIT_KEY`, read off `VIEW_SHORTCUTS`) to "Fit sketch" while a sketch is open; `viewShortcuts()` labels it "Fit to the model" unconditionally, which is also wrong in that state.

<a id="item-nextstep-comment-stale-1"></a>

### NEXTSTEP-COMMENT-STALE-1

*kind: item-story*

kind: cleanup (doc/DRY). The module doc says the dot "deliberately carries no word, no key chip and no colour of its own" — true when written, false since `bc53e7d` (groom pass 27) gave the resting dot a NEXT+label+key stamp on hover/focus/once-per-step. Separately, `REPEAT_ROWS[].label` (e.g. `"Extrude"`) is a second hardcoded copy of the word each `ToolButton` already carries via its own `label` prop in `CreateStrip.tsx` — the two can drift (nextStep.ts is used only to lower-case it into a caption, e.g. "Another extrude on this body").

<a id="item-screenshot-refresh-sketch-fit-1"></a>

### SCREENSHOT-REFRESH-SKETCH-FIT-1

*kind: item-story*

kind: process (screenshot currency). Founder screenshots are refresh-on- demand (CLAUDE.md), not regenerated per-run, so they silently drift behind the product; the sketch-mode shots now predate the Fit control and the current next-step note grammar.

<a id="item-area-integration-1"></a>

### AREA-INTEGRATION-1

*kind: item-story*

kind: known limitation (tracked, not silently dropped). MEASURED: the adaptive area integrator does NOT converge on the KUKA import — it moves from 1.74e-05 to 2.91e-05 between eps 1e-8 and 1e-10, i.e. the change is the SIZE of the signal, not noise around a stable answer — at ~11s extra cost. Trading a known small bias for an unconverged number at double the price is not an improvement, so F1's fix (`f7cd483`) deliberately left `measure_shape`'s area path on the fixed-order integrator and pinned the decision visibly via the new `loft-spline-sections-nurbs-h30` golden.

<a id="item-gen-check-verdict-1"></a>

### GEN-CHECK-VERDICT-1

*kind: item-story*

kind: defect (gate legibility). `153cfa6` added a third diff (`packages/loft-script/src/loft/_operations.py`) to `scripts/gen-check.sh`, but the success line still reads `gen-check: contracts + ts-client match generated output.` — a reader cannot tell from the message whether the Python operation table was checked at all.

<a id="item-docs-explorer-1"></a>

### DOCS-EXPLORER-1

*kind: item-story*

kind: question (product/DX decision). `725bc4b` set `docs_url=None`/`redoc_url=None` to fix the air-gap claim (Swagger/ReDoc pulled `cdn.jsdelivr.net`/Google Fonts on the published port); a contributor hitting `/docs` now gets a bare 404 with no explanation and QUICKSTART does not mention the explorer at all. Three options, in cost order: (a) one QUICKSTART line pointing at `/openapi.json` and explaining the explorer is off deliberately (cheapest); (b) serve `/docs`/`/redoc` only when `LOFT_ENV=dev` (the posture switch already exists, and the air-gap claim is about a PUBLISHED gateway, not a developer's laptop); (c) vendor the ~3MB of swagger-ui assets so the explorer works fully air-gapped even in production (most expensive, most complete).

<a id="item-shard-manifest-ci-1"></a>

### SHARD-MANIFEST-CI-1

*kind: item-story*

kind: capability (process/tooling accuracy). Found by the orchestrator, groom pass 19, while verifying CI-BAL's headroom claim on a real CI run: the local-box manifest predicted a 1.05x shard spread and 2.1x step-cap headroom; the real GitHub Actions runner measured a 1.16x spread and 1.55x headroom — still a large improvement over the count-based cut's 1.58x, but a materially different number from what was shipped, because per-file cost RATIOS (not just absolute walls) shift between this container and the runner. FIX: seed `e2e-durations.json` from CI's own uploaded JSON reports (the `e2e-shard-plan.py --emit-durations` path already exists locally; extend it, or a new workflow step, to consume `playwright-report` artifacts from a recent green `e2e` run instead of a local `--self-test`/local measurement).

<a id="item-qa-ci4-lines-1"></a>

### QA-CI4-LINES-1

*kind: item-story*

kind: defect (tooling). Measured by the CI-4 QA pass (2026-08-29) across five shard-3/4 runs at the same commit: `parts-home.spec.ts`'s "create → list → open → back → delete → persists" reports line 18 in four runs and 12 in the fifth; ten of shard 3/4's 25 files are affected; and the list reporter printed `qa-reach-batch.spec.ts:1290` for a test whose JSON report said 1448 and whose source says 1448. Nothing was misdiagnosed in that pass — both CI-red tests reported their true line — but the job log is the ONLY channel into a red CI shard, so a reader chasing a line can land in the wrong test, and `e2e-verdict.py`'s list-output fallback path would carry the wrong number into the verdict block. FIX: find the mechanism (transform-cache state is the obvious suspect and is unproven), and meanwhile make the verdict block identify tests by TITLE with the line as secondary.

<a id="item-invariants-projection-1"></a>

### INVARIANTS-PROJECTION-1

*kind: item-story*

kind: capability (DRY — CLAUDE.md: "extract on the second real use, not the first imagined one"). Flagged by the SEL-6 qa-tester agent (`153681b`) while building `qa-sel6-verify`'s occlusion-region control: it needed the same orthographic/perspective camera-projection reasoning `projection.spec.ts` already carries privately, and duplicated the minimum needed rather than importing it, since it lives in a spec file, not a shared helper. FIX: move the helper into `apps/web/e2e/invariants.ts` (this repo's existing home for shared e2e assertions) and have both `projection.spec.ts` and `qa-sel6-verify`'s occlusion control import it.

<a id="item-pgtest-gate-vacuous-nongoal"></a>

### PGTEST-GATE-VACUOUS-NONGOAL

*kind: item-story*

kind: process note (deliberate non-goal, not a gap to close). PGTEST-GATE (`ef5d1c5`) made a silent 37%-skip loud, but there is no failing floor for the vacuous case where a real server is available and the pg-marked tests happen to be deselected to zero (e.g. `-k` filtering them all out) — the verdict prints `NOTE: no test asked for a database this run` and the report/verdict cross-check refuses on disagreement, but a hardcoded "must serve >= N" count would rot the moment the suite's pg test count changes, becoming exactly the kind of gate-cannot-fail vacuity GATE-FLOOR exists to catch elsewhere. This item exists so a future pass does not "fix" the non-goal with a magic number: the correct floor for THIS case is the existing whole-suite test-count floor (`services/documents/tests/` collected count), not a pg-specific one layered on top of it.

<a id="item-audit-housekeeping"></a>

### AUDIT-HOUSEKEEPING

*kind: item-story*

(a) `git worktree prune` + `git branch -D worktree-agent-*` at batch end — 16 abandoned worktrees measured at 7.0 GB of 21 GB free, all sixteen verified 0 commits ahead of origin (nothing stranded); add the `rev-list --count origin/<branch>.. <worktree-branch>` check to the loop's Integrate phase (the worktree sweep is the one item here with a clock on it — disk). (b) 23 of 100 SHAs cited across ROADMAP+BACKLOG do not resolve to any commit object in this repo (`git cat-file -e <sha>^{commit}` fails) — a grooming sweep to prune or correct dead citations. (c) anchor `viewport-makeover.spec.ts:373`'s surviving `waitForTimeout(1200)` to a render-tick wait instead. (d) `check-compose.py:156-161`'s dev-overlay half is still a hand-list beside a half that sweeps every service — unify. (e) no `alembic check` fast gate for the gateway (1 migration, 1 table, `Base.metadata.create_all`-tested — model/ migration drift is invisible until `deploy-path`; documents already has the equivalent). (f) `services/gateway/tests/ test_assembly_import_chain.py:56` is the one place a kernel (`build123d`) import leaks outside `services/geometry` — move behind `pytest.importorskip` or a committed fixture file.

<a id="item-qa-review-owner"></a>

### QA-REVIEW-OWNER

*kind: item-story*

kind: defect (process). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 7" M9): `docs/QA-REVIEW.md` + `docs/PERF.md` are both 20 days stale with no agent definition writing them (`grep -rn QA-REVIEW .claude/agents/` → no matches), while `qa-tester` runs every non-kernel batch and its findings go into return reports instead of the repo. FIX: either give `qa-tester` `docs/QA-REVIEW.md` explicitly in its agent definition, or delete the file so nothing cites a document nobody maintains; fix `qa-tester.md:16-19`'s "both projects" instruction to match TOUCH-1's reality (no `projects` array exists).

<a id="item-gqa-2"></a>

### GQA-2

*kind: item-story*

kind: defect. `_signature_dto` emits all three `outer_*` fields as `None` both when a pre-2026-08-16 selector never had them AND when `outer_boundary_invariants()` fails at pick time — the resolver keys the dual-read purely on field PRESENCE, silently taking the weaker inferred-band path in both cases. The wrapper already carries `selector_version: 1`, the field that exists to make this distinguishable, and it isn't used. Narrow today (needs a live OCCT region-build failure at pick time to matter) but will directly block a future document-side re-emit from knowing which stored selectors it has already upgraded. FIX: stamp `selector_version` (or a dedicated reason field) when the outer-boundary build fails, distinct from "never computed."

<a id="item-gqa-3"></a>

### GQA-3

*kind: item-story*

kind: defect (perf regression, filed not blocking — two orders inside the ceiling). MEASURED warm, three goldens: `sketch-extrude-plate-6hole-ring-cut-60x60x10` 18.08ms -> 21.71ms (+20%), `pattern-cut-6hole-boltcircle-60x60x10` 18.18ms -> 21.52ms (+18%), `revise-lightened-plate-...-100x100x14` 15.65ms -> 19.09ms (+22%). `planar_faces` runs on the overlay route — the one every viewport click hits, budgeted since audit H4 — not only on the GEOM-3 rescue path, so §12a's "a clean rebuild pays nothing" no longer holds there. Lever already measured and identified: `BRepBuilderAPI_MakeFace(gp_Pln, wire)` (0.249 ms) vs `Face(wire)`'s 0.686 ms on the 64-hole face — swap the outer-boundary-invariant construction to the cheaper API on the overlay's hot path.

<a id="item-gqa-4"></a>

### GQA-4

*kind: item-story*

kind: capability (test-coverage gap). MEASURED (`docs/AUDIT-ENGINEERING.md` "Pass 9" N7): solving all 75 golden sketches through `PlanegcsSketchSolver` shows 70/75 route through `settle()`, and the batch changed zero golden bytes — evidence the fast path (`_try_hold_everything`) succeeds on all of them because their stored coordinates already solve. None exercises rungs 1-4, the orientation guard, or the drift condition — only the three new unit files' synthetic fixtures do. FIX: add a golden whose sketch is deliberately edited off its stored solution (one dimension changed, so the fast path must fail and the ladder must run), putting the ladder under the determinism gate for the first time.

<a id="item-rev-3"></a>

### REV-3

*kind: item-story*

(`apps/web/components/FloatingPanel.tsx:94-95`). Filed 2026-08-13; MEASURED in Chromium against the repo's real Tailwind build. `railed ? "shrink-0 self-start"` has no side branch, unlike every other side-aware clause in the file. At 1280x650 with a 320px card docked above: rail `right=1268`, tab `right=1049.8` — 218 px of empty column to the right of a tab on a `right-3`-anchored rail, and a behaviour change from the floating case, which pinned it to `right-3`.

<a id="item-rev-4"></a>

### REV-4

*kind: item-story*

(`apps/web`, `scripts`). Filed 2026-08-13 from the review's claims audit. Each is small; batched so they are fixed once. (a) `support.ts:550-552` — "NEVER SLOWER THAN ITS PREDECESSOR" is false and self-contradicting two clauses later. The predecessor raced n rAFs against a 2 s timeout; the successor has a 15 s ceiling and no shortcut. MEASURED: `waitForFrames(page, 30)` took **2317.7 ms** in a quiet window. Correct form: never waits fewer FRAMES; wall clock can be longer, by design. (b) `ChromeRail.tsx:53-59` — the stated reason for context-over-ref is wrong in both halves: the shipped `useState`+`useEffect` path is ALSO null on first commit, and a plain ref would float forever, not "for one frame". The code is right; the reason is not. (c) `support.ts:292` — constants "exported so a spec can state what it calibrated against"; no spec imports them and the calibration comment never names 0.25 or 24. (d) `e2e-shard-audit.py` — the `"timedOut" in self.statuses` branch is dead (Playwright's JSON reporter serialises a timeout as `unexpected`, already covered); harmless, but say so or delete it. (e) `e2e-shard-audit.py` timeline — "N tests" / "% of the way through" counts only tests that RAN; skipped tests have `results: []` and vanish. (f) `e2e.yml:204` — "a job timeout kills the `if: always()` upload steps" is REASONING ONLY and unmeasurable from this container; GitHub documents `always()` as running on cancellation.

<a id="item-spec-3"></a>

### SPEC-3

*kind: item-story*

(`apps/web`). Filed 2026-08-11 by the orchestrator. `45c8592`'s e2e went red on `interaction-depth.spec.ts:40` at `Expected > 336, Received 316`; the assertion is `distinctCanvasColors(page) > inkColors + 8`. WHY THE GATE AND NOT THE FEATURE: the raster-INDEPENDENT hook asserted immediately above it — `extrude-preview-active` attached with `data-distance-mm="10"` — PASSED, so the ghost was present. The descendant `7ffac16` then ran the same spec GREEN on the same tree. WHY IT IS FRAGILE: `distinctCanvasColors` (`support.ts:345`) samples every 16th pixel and counts distinct RGB, so it is an AA- and framing-sensitive statistic. The assertion is a NET — colours the ghost ADDS minus any the extrude editor REMOVES (sketch grid/plane) — and +8 is a thin margin on a difference.

<a id="item-sel-6-aftercare"></a>

### SEL-6-AFTERCARE

*kind: item-story*

(`apps/web`). Filed 2026-08-08 by the orchestrator. None blocks anything; batched so they are fixed once rather than rediscovered five times. (a) `pickRaycast.ts:6` — the evidence numbers DISAGREE for the same pre-fix census: the commit message and `docs/ROADMAP.md` say 7.4% -> 96.3% (control 96.7%), the module header and `pick-affordance.spec.ts:601` say 8.5% (27/317, control 98.0%). Probably pre/post the unlit luminance-proxy correction, but this repo's standard is measured numbers that AGREE — name the run each came from or reconcile them. (b) `ModelMesh.tsx:207` — a fifth copy of the stale reason survived the four-copy sweep; the comment still credits a pointer-handler refusal SEL-6 deleted, and the `!bodyFaceState.hidden.has(hoveredFace)` guard at :220 is now dead ( harmless as defence-in-depth, but say so). (c) `hiddenPicks.ts:83` — every mounting overlay builds its own weld-bucket Map, so two live overlays mean duplicate O(V) passes with string allocation; free today via the OFFER_EVERYTHING short-circuit, but derive it once beside `pickHiddenFaces` in `partView.ts` if it shows on a heavy part. (d) `EdgePickOverlay.tsx:56` — `FacePickOverlay` drops its hover when the offer changes; `EdgePickOverlay`, `ShellFaceOverlay` and `MeasureOverlay` do not, so the QA stamps the e2e gates read can carry a withheld entity's index for one frame.

<a id="item-sel-5"></a>

### SEL-5

*kind: item-story*

(`apps/web`).

<a id="meta-later-fb-3-fb-5-reproduce-32-of-145"></a>

### **FB-3/FB-5 reproduce**: 32 of 1457 sample points (**2.2 %**

*kind: meta-story*

: 32 of 1457 sample points (**2.2 %**) over the body are live face targets; the other 97.8 % is dead, and the markers for hidden faces draw over the visible ones. **FB-6's z-fighting

<a id="item-sel-5-2"></a>

### SEL-5

*kind: item-story*

(`packages/design`).

<a id="item-conc-5"></a>

### CONC-5

*kind: item-story*

(kernel, likely upstream).

<a id="item-conc-7"></a>

### CONC-7

*kind: item-story*

(backend).

<a id="item-p3-s-ws3-drag-a-register-r"></a>

### - [ ] (P3, S) **#WS3 — drag a register row onto a divider to

*kind: item-story*

#WS2 shipped MOVE as a verb (a select of every folder by path) and deliberately did NOT ship drag: a filing gesture reachable only by pointer would put the product's one rearrangement out of keyboard reach, so the keyboard path had to be the primary one and is complete on its own.

<a id="item-p2-m-web-authoring-for-the-mi"></a>

### - [ ] (P2, M) **Web authoring for the mirror scope** (fronte

*kind: item-story*

(frontend; unblocked by the kernel above). Two radio buttons ("Mirror: body / features") plus a feature-tree multi-select; `scope` is OPTIONAL in the generated client (`scope?: MirrorBodyScope | MirrorFeaturesScope`), so existing callers are unchanged and only the new UI sends it.

<a id="item-p3-s-the-v1-cut-slot-still-re"></a>

### - [ ] (P3, S) **The v1 cut slot still records only extrude-c

*kind: item-story*

v2's per-feature store covers every mirrorable verb, but `record_cut_tools` — which `body`-scope mirror and `pattern` read — was deliberately NOT widened (mirror-semantics §6.2: doing so silently changes what those two reflect on trees with shipped goldens).

<a id="item-qa3-4"></a>

### QA3-4

*kind: item-story*

`OverlayFace.feature_id`'s description (py-kit → `packages/contracts/gateway.openapi.json`) tells clients "each face's `index` is its `body.faces()` ordinal (== the GLB primitive ordinal, one glTF primitive per B-rep face)".

<a id="item-qa3-5"></a>

### QA3-5

*kind: item-story*

(geometry). Every cylindrical face gets 126 circumferential segments whatever its radius. Measured max chord error against the 0.1 mm `DEFAULT_LINEAR_DEFLECTION`: Ø3 hole 0.000467 mm (214x finer), Ø5.2 bore 0.000808 (124x), Ø10 bore 0.001554 (64x), Ø22 boss 0.003419 (29x).

<a id="closed-later-x-p3-xs-max-provenance-face"></a>

### - [x] (P3, XS) **`MAX_PROVENANCE_FACES`' docstring still fil

*kind: closed*

- [x] (P3, XS) **`MAX_PROVENANCE_FACES`' docstring still files a fix that shipped.** DONE 2026-08-01 (orchestrator, same day it was filed): the four lines now describe the shipped design — attribution is O(final faces) since PERF-5b — and say what is still TRUE of the arithmetic, namely that the budget counts summed snapshot faces because that bounds the work of PRODUCING the fingerprints. So 30 000 is headroom against the recording pass, not against a quadratic attribution pass. Filed by kernel-architect, which correctly declined to reach into `packages/**` outside its territory.

<a id="item-p3-s-a-lost-dimension-s-capti"></a>

### - [ ] (P3, S) **A lost dimension's caption can overrun into 

*kind: item-story*

(kernel/drawings). `DimensionGlyph` now stamps the server's `ComposedDimensionError.message` at `dim.text`, which is right; the placement is not. `compose.py`'s `_DIM_ERROR_TEXT_DX` offsets the caption by a fixed amount with no width measurement and no collision check against the neighbouring view's extents, so a long message crosses the gutter. Visible in `docs/screenshots/drawing-dim-lost-after-1440.png`.

<a id="item-p3-s-step-import-parse-worker"></a>

### - [ ] (P3, S) STEP import parse-worker — cap parse WORKING-S

*kind: item-story*

only the 16 MiB _input_ is capped, so an adversarial <16 MiB file can still balloon OCCT's in-memory model.

<a id="item-spec-2"></a>

### SPEC-2

*kind: item-story*

(`apps/web/e2e`).

<a id="item-a11y-sketchstrip-dup-1"></a>

### A11Y-SKETCHSTRIP-DUP-1

*kind: item-story*

kind: polish. Surfaced by A11Y-TOOLBTN-1's blast-radius enumeration, from Chrome's own accessibility tree on the real stack: `sketch-exit` announces name "Exit sketch and discard 4 unsaved entities — asks first" and description "discards 4"; `sketch-discard-confirm` name "…— this cannot be undone" and caption "cannot be undone"; `sketch-save` (bound) name "Finish sketch (edits are already saved)" and caption "edits save live". These `aria-label`s are NOT the ExportToolGroup workaround — they are deliberate FB-13 flow copy that predates the primitive fix and reads well on its own — so they were left alone rather than churned by a builder whose ticket was the primitive. The redundancy is the SAFE direction (both channels agree; many AT configurations suppress descriptions entirely), which is why this is P3 and not P2. FIX: decide per button whether the consequence belongs to the name or the description and say it once; the primitive's doc comment now states the rule ("do not fold a caption's words into `aria-label`").

<a id="closed-blocked-done"></a>

### DONE

*kind: closed*

- [x] (P2, S) Verify full `docker compose up` runtime — **DONE 2026-07-25** (platform-builder): unblocked by running it where Docker works, CI — `deploy-path` run `30142627371`, `success`, 86s, 9 checks passed. `scripts/compose-smoke.sh` (workflow `deploy-path`, `just compose-smoke`) builds + boots the base stack, migrates both schemas from the images, drives register → sketch → extrude → evaluate → mesh fetch → STEP export over the gateway port only, and asserts the internal ports are closed. Found + fixed: gateway/documents shared one database although both alembic trees start at revision `0001` (second migration silently no-ops), and no host-toolchain-free way to create the schema. [src: roadmap]

<a id="item-p2-xs-fill-in-e2e-yml-88-an"></a>

### - [ ] (P2, XS) **Fill in `e2e.yml:88` and `ci.yml:83`'s CI n

*kind: item-story*

(`docs/AUDIT-ENGINEERING.md` "Pass 7" M5+M10) — orchestrator-only, a CI read no subagent can perform. Browser suite: 547 tests, ~20 min/shard extrapolated (was 352 when the "raise matrix to 6 past 30 min" rule was set; +55% in 20 days, 30 min/shard arrives in ~3 weeks — `e2e-shard-audit.py --timeline` has printed this on every run for ten days, unread). Python job: `just test` measured locally at 3735 passed / 1 skipped / 1280.7s (21m20s), against a 30-min ceiling argued from ~2958 tests/14m31s. **Orchestrator-read CI number, groom pass 26: the geometry (`python`) job ran 21m57s on a real CI run** — confirms the local 21m20s estimate rather than superseding it (both now inside ~2 min of each other), and the margin against the 30-min ceiling is ~27%, down from the original measurement's much wider gap.

<a id="done-archive"></a>

### Done — archive (moved verbatim)

*kind: done-archive*

## Done — archive

One line per item once its phase has closed (id, one clause, commit/evidence); full narrative lives in the commit message and, where noted, `docs/CHANGELOG.md`.

### Groom pass 32 (2026-09-24, backlog-groomer — helical-gear kernel/UX gaps closed; geometry-QA verified the twisted extrude; 13 items filed)

- **Kernel: helical sweep -> threads/gears (G1)** (`d823af9`+`debd5b7`+`87d099f`+`43ab526`+`cbc5720`+`000cc4d`, geometry-QA `a83d53a`+`e686107`) — twisted extrude ships, verified exact against a closed-form truth. - **SKETCH-TYPED-POINT-1 (G2)** (`e4d5805`) — typed X/Y while placing + configurable grid step. - **SKETCH-VIEW-RESET-1 (G3)** (`fc5e840`) — a sketch edit no longer re-frames the view. - **SKETCH-GLYPH-HITTEST-1 (G4)** (`09cb3d8`) — a label click no longer lands at the canvas corner. - **SKETCH-ENTITY-DELETE-1 (G7) + UNDO-BUSY-LABEL-1 (G12)** (`851d6ef`) — entity delete + trim/nonce fix, same root cause as the stuck Undo. - **SKETCH-ARC-SNAP-GAP-1 (G8)** (`f57111d`) — open profile ends marked, gap named. - **SESSION-TTL-REFRESH-1 (G6)** (`cd6baed`+`3c18833`+6 review fixes) — sliding sessions replace the 1-hour hard expiry. - **Extrude editor keeps twist on edit** (`8c0ec52`). - **CI: MinIO built from source** (`78cca5b`) — Docker Hub and quay.io both withdrew prebuilt images. - **CI: metrics-seams flake fixed** (`5ef2db0`).

Filed: TWIST-VOLUME-INTEGRATOR-1, TWIST-EXTRUDE-UI-1, QUERY-CACHE-USER-SWITCH-1, AUTH-REGISTER-RATELIMIT-1 (Ready); TWIST-TESSELLATION-PERF-1, AUTH-SHORT-TTL-E2E-1, DEEPLINK-SIGNIN-RETURN-1, LOFT-ERROR-COPY-1, SKETCH-DELETE-DRY-1, CRAFT-12-PANEL-ZOOM-1 (Next P2); TWIST-ORIENT-INSIDE-OUT-1, FEATURE-TREE-ROW-CLIP-1, AUDIT-ENGINEERING-MINIO-STALE-1 (Later P3); MINIO-LICENSE-REVIEW-1 annotated, not new (see Ready).

### Groom pass 31 (2026-09-24, backlog-groomer — helical-gear product test filed; STEPNAME-1/1B/2 closed; EDGE-RESOLVE-WARN-1 kernel half closed)

- **STEPNAME-1 / STEPNAME-1B / STEPNAME-2** (`5220841`+`95dd9cd`, plus the earlier kernel/single-body fixes already archived above) — FULLY CLOSED: the web builds the assembly evaluate request WITH each instance's name (`5220841`, 2026-08-29); `95dd9cd` (2026-09-24) pins the audit's exact two-PRODUCT case ("Chassis bracket", "Mounting plate") in the exported bytes AND via an XCAF read-back import, closing the acceptance criterion the original ticket asked for. Found in passing: `services/documents/src/documents/step_import.py` names an imported PART after the occurrence label ("Chassis bracket <1>") rather than the product ("Chassis bracket") — filed as STEPIMPORT-PART-NAME-1 (see BACKLOG.md Next (P2)). - **EDGE-RESOLVE-WARN-1 kernel half** (`6bf58e0`, design doc `1aa7b17`) — `FeatureResult.subshape_resolution` reports which tier (`exact`/`durable`/`adjacent`) re-found each picked reference on a rebuild; additive, never blocks. Web half (surfacing it in the tree/banner) remains Ready.

Filed from `docs/qa/helical-gear-2026-09-24.md` (16 ranked gaps, first live product test of a complex helical part; tested at `95dd9cd`): SKETCH-TYPED-POINT-1, SKETCH-VIEW-RESET-1, SKETCH-GLYPH-HITTEST-1, SKETCH-EXPR-FUNCTIONS-1, SKETCH-ENTITY-DELETE-1, SKETCH-ARC-SNAP-GAP-1, SESSION-TTL-REFRESH-1 (IN FLIGHT), SKETCH-DIM-POINT-DISTANCE-1, CHAMFER-FACE-LOOP-SELECT-1, PATTERN-LOFT-EVAL-COST-1, UNDO-BUSY-LABEL-1, SKETCH-CIRCLE-RUBBERBAND-TYPE-1, LOFT-EDITOR-PRESELECT-1, CHAMFER-ERROR-COPY-1, LOFT-BSPLINE-OPTION-1, STEPIMPORT-PART-NAME-1 (see BACKLOG.md Ready/Next/Later). The existing "Kernel: helical sweep -> threads" item (Next (P2)) was raised P2->P1 and annotated with the report's measured helix-error numbers; it is IN FLIGHT with another agent, not Ready.

### Groom pass 30 (2026-09-24, backlog-groomer — W0REV-3, MEASURE-LABEL-PITCH-1, PERF-REAL-1, reused-id PERF-REAL-3 all closed; CI green through 9c21801)

- **W0REV-3** (`87daed6`+`caebc10`) — sketch drafts now sweep (expiry, then oldest-first, ≤20 drafts/2 MiB); the session write evicts drafts on quota instead of failing silently; a new `packages/design` `Notice` primitive shows the failure to the user (top-bar strip + sign-in warning). - **MEASURE-LABEL-PITCH-1** (`dc49558`) — a picked circle's hero reading is centre-to-centre, labelled and distinct from the kernel's raw minimum-distance reading; edge labels carry coordinates. Verified 25.0mm pitch vs 17.0mm min on a known plate; no wire change (derived from each edge's existing stage-1 signature). - **PERF-REAL-1** (`a785d84`+`ac568b7`+`fafbf78`+`14838cb`) — a BVH replaces the brute-force per-face raycast (22ms->0.2ms/ray, 0 mismatches over 19,800 rays in review); on `gearbox-11752`, arm->prompt 42-48s->~11s, click->sketch-on-face ~31s->8-15s, mark settle never->~34-36s. `fafbf78` fixed a real bug the speed-up exposed: the part rig's auto-fit was posing the camera while the sketcher owned it. - **PERF-REAL-3 (reused id, overlay cache-key collision — distinct from the still-open mesh-payload PERF-REAL-3)** (`496d275`+`989349c`+`9c21801`) — `record_history` came out of the rebuild-cache key so a face pick after an evaluate is a cache hit, not a guaranteed miss; overlay after evaluate 8.8s->~2.1s via the gateway, recording costs 0.06-1.6% of a cold rebuild.

Filed: GAUNTLET-BROWSER-CI-1, EDGE-BAND-RAYCAST-BVH-1, OVERLAY-CACHE-HIT-RESIDUAL-1, STEP-IMPORT-CACHE-1, GAUGE-POINTERUP-FLAKE-1, E2E-DURATIONS-MANIFEST-1, MEASURE-CIRCLE-STRAIGHT-EDGE-1, LINEAGES-DOCSTRING-STALE-1, SESSION-EXPIRED-NOTICE-1 (see BACKLOG.md Next (P2)).

### Groom pass 29 (2026-09-24, backlog-groomer — PICK-PROXY-COLLIDE-1, CONTRACT-PARITY-TEST-1, PERF-REAL-2, E2E-SHARD-COUNT-1, QA-CUBE-YIELD-SETTLE-1/FB-7 all closed; CI green through d3d0446)

- **PICK-PROXY-COLLIDE-1** (`9404cb1`+`b9d2a78`) — pick marks publish real seats, buried marks draw dashed, gauges keep out the marks they'd cover; census 0 lies (was 7 live-but-buried on Fillet alone). - **CONTRACT-PARITY-TEST-1** (`647f939`) — expected set now derived from the OpenAPI doc directly, 0 mismatches over 86 ops; `part.py:317` confirmed already fixed by `43c03a1`, not deliberate. - **PERF-REAL-2** (`09416c6`+`4fcb108`+`560eab1`+`8e9e5c8`+`8077ede`+`83e3c67`) — checkpoint ladder, edit #249 34.1s->1.85s (18.5x, QA-measured); both rebuild caches now byte-bounded (ladder 64 MiB, frontier 128 MiB + one oversize checkpoint held alone); early-edit floor refiled as PERF-REAL-2B. - **E2E-SHARD-COUNT-1** (`d3d0446`) — 6 shards, ~22.6 predicted CI-min/shard, confirmed on a real run by `55df4d3` (8 jobs, 0 failed). - **QA-CUBE-YIELD-SETTLE-1 / FB-7 flake** (`d0604c5`+`856e3c0`) — shared root cause (sketch-exit fit reading the restore ease's in-flight direction) fixed; rest elevation now 23.11 deg, 0.00 deg off. - **`9b1e45f`** — one shared `waitForCameraStill` in `invariants.ts`, also fixed a live defect (pick-proxy-collision never installed the camera probe it read).

Filed: GAUGE-READOUT-TAG-1, FACE-HOVER-BORE-FLAKE-1, PERF-REAL-2B, FRONTIER-OVERSIZE-SIDESLOT-1, PICK-SPEC-REWEIGH-1, LADDER-PROVENANCE-WEIGH-1 (see Ready/Later).

### Groom pass 27 (2026-09-23, backlog-groomer — known e2e failures fixed, F-6 closed, gauge-lag closed)

- **F-6 (hole CREATE lets through a known-off-face point)** (`503473c`+   `b99e4e4`+`37e6e18`) — a veto tried then withdrawn on measurement; the   commit control now carries the placement warning live, and the X/Y   fields' zero is named above them. Never filed as an open ticket; closed   the same audit cycle it was found. - **Gauge/panel one-commit lag** (`3b7f9ad`+`357b91e`) — `useGaugeFedForm`   generalises the render-phase write fix (see CRAFT-13 follow-up above) to   all nine gauge-fed mounts. - **F-11 Fit while sketching** (`f9fcce6`) — the view rail's Fit key frames   the open sketch instead of unmounting entirely; opened a real regression   in its own wake (`CONSTRAINTS-GLYPH-1280-1`, filed AND closed same pass   by `5444fa8` — a canvas click DRAWS while sketching, and the Fit bar's   bottom-centre seat sat on the sketch rig's own -Y axis; moved to hang off   the reference cube instead). - **Next-step dot gains a word** (`bc53e7d`) — the band's resting proposal   now speaks on hover/focus/once-per-step, reusing the viewport's own   leader-note grammar. - **REASON-GATE-1 straggler** (`17763b5`) — see REASON-GATE-1 follow-up   above (`OffsetPlanePanel` was outside the original 15-editor survey). - **GHOST-1 residual** (`0d96454`) — see GHOST-1 follow-up above (an   unsplittable part stayed opaque during a sketch edit). - **e2e known failures + shard-4 timeout** (`202cc9d`, `9375cb3`, `3b7f9ad`,   `36360ae`, `8f8adc2`, `004755d`, `7c9ff95`, `5444fa8`) — see ROADMAP   "Current focus"; CI verification owed.

Filed: CONSTRAINTS-GLYPH-1280-1 (closed same pass), QA-CUBE-YIELD-SETTLE-1, FILLET-GAUGE-FPS-FLOOR-1, PATTERN-SCOPE-TIMEOUT-1, SCREENSHOT-REFRESH-SKETCH-FIT-1, DATUM-DEADCODE-1, SHORTCUT-SHEET-SKETCH-FIT-1, VIEWBAR-DRY-1, SKETCH-FIT-GRID-OCCLUDE-1, NEXTSTEP-COMMENT-STALE-1, E2E-SHARD-COUNT-1 (see Ready/Next).

### Groom pass 25 (2026-09-15, backlog-groomer — Phase 5 flagship + gauntlet F1/F2 + CRAFT-13)

- **SCRIPT-1** (`153cfa6`+`ca2f9d9`+`14f6e14`+`43c03a1`) — public Python   scripting API, two-path-proven identical to a browser-driven build (12/12   facts, byte-equal STEP/STL); `packages/loft-wire` split (33→15 deps). - **F1 (wrong volume) + F2 (mesh_glb_id non-determinism)** (`f7cd483`) —   adaptive integration at swept `VOLUME_EPS=1e-10`; cache paths unified. - **CRAFT-13** (`b4e7821`) — root cause was a pointer-capture P0 (arc gauge's   hit sleeve unmounting its capture host mid-drag), plus an unstated settle   masquerading as the `craft9b-gauges` contract-β intermittent. - **Air-gap claim** (`725bc4b`) — Swagger/ReDoc explorer pulled 3rd-party   CDN/fonts on the self-hosted port; `docs_url=None`+`check-air-gap.py`. - **Self-host web service** (`977f492`+`093dfc1`) — a `web` (nginx+SPA)   service existed nowhere before; two guard-manufactured CI failures fixed   en route (root-owned nginx pidfile, invalid job-level `runner` context). - **Scorecard freshness gate** (`b1bb1b6`) — mechanical staleness check for   `docs/VISION.md`'s scorecard, advisory only.

Filed: PERF-REAL-1, PERF-REAL-2, VEC3-DEDUP-1, CONTRACT-PARITY-TEST-1, SCOREFRESH-PENDING-1, REQUIRED-QUERY-1, GAUGE-QUIESCE-1, NURBS-FIXTURE-1, STEP-ROUNDTRIP-COVERAGE-1, PERF-REAL-3, AREA-INTEGRATION-1, GEN-CHECK-VERDICT-1, DOCS-EXPLORER-1, CSP-1, PERF-ASM-1, PICK-ASM-1, BOM-ASM-1 (replaces the old flat-BOM entry), FLOW-ASM-1 (see Ready/Next/Later). Full detail: "Scorecard gaps" above and `docs/CODE-REVIEW.md`/`docs/GEOMETRY-QA.md`.

### Groom pass 20 (2026-09-13, backlog-groomer — frontend-redesign W0/W0REV/W2 reconciled onto BACKLOG)

- **W0REV modal-gate fix** (`da98622`) — one capture-phase `modalGate.ts` closes 3 findings: Enter-on-exit-prompt applying the armed dimension, save-in-flight focus loss, sketch drafts outliving sign-out. - **FLOW-B1/B2/B3** (`d5e936a`, `78aaa67`, `fb63809`+`6097448`) — accelerators for the 5 core verbs, a solved-sketch Extrude proposal, one accented next-verb after a build. - **CRAFT-6** (`a340ff5`) — the reference cube persists through plane-pick and sketch. - **CRAFT-1/2/3** (`57d3bf8`) — a filleted body draws its edges, an orthographic view keeps its ground plane, the origin triad draws at rest. - **MinIO repointed to quay.io** (`bd58416`, ROADMAP-only) — Docker Hub withdrew `minio/minio`/`minio/mc`; fixed 3 red CI jobs.

Filed: MINIO-LICENSE-REVIEW-1, FLOW-JOURNEY-GAP-1, GRIDMINOR-TONEMAP-1, MODALGATE-MIGRATION-1, AXISLABEL-ORTHO-1, VIEWFRONT-ORTHO-DECISION-1 (see Ready/Next). Full detail: `docs/CHANGELOG.md`.

### SEL-2 CLOSED (2026-09-04, frontend-builder)

- **SEL-2** — hover now names the entity a click will take (extended marker on a line with no closer point); one `CursorMark` serves drawing and selecting. Shots: `docs/screenshots/sel2-pick-marker-*-1280.png`.

### Groom pass 19 closures (2026-08-29, backlog-groomer — CI-4's original question answered, K2 + PBT-1 land)

- **K2** (backend-builder) — route-auth posture gate confirms gateway/documents/geometry posture already correct (four audit passes asked for this). - **PBT-1** (kernel-architect) — sketch-solver 2000-trial seeded corpus; the 7-of-155 violated-constraint headline re-measures at 0. Found SOLVE-CRASH-1 (fixed below), SOLVE-CONFLICT-MOVED-1, SOLVE-OVERCONSTRAINED-AMBIGUOUS-1 (still open). - **SOLVE-CRASH-1** (kernel-architect, arbitrated P2→P1) — an untyped 500 driving a circle's radius through zero: 3 real negative-radius solves fixed, 9 annihilated circles now return `sketch_conflicting`. - **CI-4's original question** (qa-tester) — the e2e suite is NOT systemically unstable; shard 3/4 was structurally overloaded by Playwright's filesystem-order file cut. Two of three shard-3/4 reds root-caused; QA-CI4-MATE-1 (unreproduced hypothesis) remains. - **CI-BAL** (platform-builder) — duration-aware shard split; corrected its own headroom claim 2.1x (local box) → 1.55x (real CI runner) — see SHARD-MANIFEST-CI-1. - **QA-CI4-HEADROOM-1** (qa-tester) — cut a redundant-work cost first (a re-parked pointer costing 47% of one test's wall), raised ceilings second, from a measured distribution. - **CI-5** (`2874f0a`) / **CI-5a** (`ecc1fb7`) (orchestrator) — a red shard's failure list now survives log-tail truncation and correctly distinguishes a declared `test.fail()` from a real failure. - **PGTEST-GATE** (`ef5d1c5`, platform-builder) — a missing PostgreSQL now fails loudly instead of silently skipping 37% of the documents suite. - **MEASURE-PROXY-1, PICKMARK-OCCLUDE-1, EXPORT-3, REACH-2-IMPORT-1, REACH-3-FLOW, REACH-2-FLOW, A11Y-TOOLBTN-1, HEM-1C, HEM-1D** (frontend-builder, 2026-08-28) — carried over from pass 18, collapsed into this archive here.

Filed: ARC-DEGENERATE-1, SHARD-MANIFEST-CI-1. Full detail: `docs/CHANGELOG.md`.

### SEL-8 CLOSED (2026-08-28, frontend-builder)

- **SEL-8** — the hover hit-test was intact all along; the highlight material lost the depth test against its own body surface and drew 0 px. Fixed with a two-pass `HighlightLines` draw; the same fix also unblinded MEASURE's identically-invisible edge highlight. See PICKMARK-OCCLUDE-1 for the half of the original finding this does NOT close.

### PANEL-DENSITY-1 CLOSED (2026-08-28, frontend-builder, founder-directed)

- **PANEL-DENSITY-1** — overlay panels (item tree, material selector) now match the header's density (row pitch 34.6px→24px). Fixed in `packages/design` primitives, not per instance; closed 3 pre-existing sub-24px touch-target violations in passing.

### Groom passes 15-18 closures (2026-08-27/28, backlog-groomer — reachability programme + HEM-1 P0)

Branch merged to `main` as `03d2eca` (141 commits, CI green) in pass 15; the reachability programme completed in pass 16 (`scripts/check-ui-parity.py`: 84/85 ops called, 97/109 literals authorable, 0 ABSENT-tier gaps — up from 39/120 literals unreachable at first measurement).

- **HEM-1** (`db05e13`, P0, wrong geometry) — a "closed" hem defaulted to the part's base-flange radius (a 6mm gap on 2mm sheet, labelled closed); now defaults to a small fraction of gauge. - **ASMDRAW-FIT-1a** (`79ca41c`) / **ASMDRAW-FIT-1b** (`69b3ef7`) — assembly-sheet solved-extents route + fit-scale off it, not the picked scale; an unsolved bbox deliberately keeps the picked scale (user-owned, no-surprise posture — a decision, not an oversight). - **EXTRUDE-COARSE-STEP-1** (`1661a5b`) — the extrude drag-handle keyboard step now quantises to the next step multiple instead of adding onto wherever a free drag left off; also fixed a queued-ack race dropping fast keypresses. - **ORTHO-1** (`9a04a6a`) — an ORTHO/PERSP toggle + orienting commands (Home/Front/Top/Right/Iso, ViewCube picks) arm orthographic; closes a gap 4 consecutive audit passes reported. - **REACH-ORDER** (`472f040`) — feature-tree reorder (drag + Alt+Up/Down keyboard), shipped-but-uncalled for weeks. - **REACH-ASMDRAW** (`02bd6ab`, `3e2d1e5`) — an assembly can now be drafted on a drawing sheet with its numbered parts BOM. - **FORCE-CLICK-AUDIT-1** (`6911352`) — 22 `force: true` e2e call sites audited: 18 were cargo (dropped), 1 was hiding a real `sr-only` visibility defect (fixed), 3 are genuine refusals (proven via new `clickRefusedControl` helper). - **DRAWING-VERTEX-PICK-1** (`fe96d9b`) — a vertex handle now claims at most a third of its shortest incident edge, so the edge keeps a reachable middle at every length. - **REVOLVE-1** (`1b28dd5`) — axis `<select>` offers all 3 world origin axes + profile edges; closed the last ABSENT-tier literal in the gateway contract. - **SKETCH-VOCAB-1 frontend half** (`38e37f5`) — constraint catalogue lists all 16 verbs (was 12); kernel half shipped pass 14. - **MATE-1** (`a2a6f9f`, gated `1ae3270`) — a buried mate face is reachable via `mateDepthStack`; closed T-13 (highlight = the face's own traced boundary). T-14 was out of scope, refiled as MEASURE-PROXY-1. - **QA-R1** (`5957252`) — fixed `Flyout`'s label-collapse primitive, not the sketch strip instance it was first reported on. - **QA-R2** (`0cee656`, e2e hardened `d2b1d26`) — the angle glyph now reads the solved value, not the authored placeholder. - **QA-R4** (`278c122`) — `derivePartBuild` takes write-in-flight + the write's own reply as inputs so a body mid-write no longer reads a stale "Up to date"; also unified the SOLVE-2-class STATUS/SOLVE cell disagreement onto one predicate. - **MATE-OBS** (`6b26ff7`) — a mate write's ~1.35s stale window no longer renders a settled answer over a superseded solve; MATE-OBS-2 (tree-panel badge, an eighth consumer) filed as a narrower follow-up. - **Four REACH-3 follow-ups** (`ef704e7`, `1e8d8a3`, `f832eae`, `ddab149`) — a placing ghost reads its own number, the offset nudge quantises instead of accumulating drift, a placed dimension is re-grabbable, and drawing pick hit-regions are real shapes instead of bare zero-height SVG strokes. - **SEL-8 id collision** — an unrelated P3 item that also used the id `SEL-8` renamed to **SEL-6-AFTERCARE** to disambiguate.

Filed this batch: ASMDRAW-FIT-1a/1b, PLAYWRIGHT-TOUCH-1, EXTRUDE-COARSE-STEP-1, HEM-1B, REACH-2-IMPORT-1, MEASURE-PROXY-1, FORCE-CLICK-AUDIT-1, MATE-OBS-2, DRAWING-VERTEX-PICK-1, SKETCH-COVERAGE-1, SOLVER-DOC-1. Confirmed still open, unchanged: REACH-3-FLOW's orientation half, TITLEBLOCK-STAMP-1, EXPORT-3, NAME-2b, REACH-2-FLOW, QA-R3. Full detail: `docs/CHANGELOG.md`.

### Groom pass 14 closures — collapsed pass 16 (full detail: `docs/CHANGELOG.md`)

- **SPEC-9/SPEC-10** (`e8702d5`/`42f6bbd`) — two more CI-4(d)-class specs   fixed (wait for armed state; assert the settled solve). - **DOCTICK-GATE** (`bd09f5b`) — CI now judges a commit range for missing   ROADMAP/BACKLOG ticks. - **SNAP-5** (`ecdf9ad`) — a near-axis-aligned line authors horizontal/   vertical at placement. - **SIGNIN-1** (`bf65ddc`) — the sign-in sheet is a bounded, centred object   (45% of frame vs. 5.2%). - **T-23/DRAG-1** (`35027ef`) — extrude gets a draggable depth gauge. - **PATTERN-1 frontend half** (`ec9c569`) — tree-row selection seeds   `PatternParamsV1.scope`; flow gaps found by review filed as REACH-2-FLOW. - **REVOLVE-1 kernel half** (`88b6074`) — three always-available world   origin axes. - **SKETCH-VOCAB-1 kernel half** — angle/diameter/midpoint/collinear/   symmetric-two-lines-and-an-axis, kernel-only (frontend half stayed open). - **Parts register resume band** (`cb2e43e`) — proposes "resume what you   were doing"; a REBUILD-column regression reverted same-night (`d0b55b2`,   the fix, not a regression to re-file — a health verdict is volatile   per-row data, unlike a stable unit column; reasoning lives in-source at   `showHealth` for the next person tempted by the same analogy).

### Groom passes 10-13 closures — collapsed pass 16 (full detail: `docs/CHANGELOG.md`)

- **SETTLE-PERF-1** (`eed8729`) — planegcs settle-ladder 883x faster (12,944ms   -> ~15ms on a 48-line edit); removed a 90s-timeout DoS route. [kernel-architect] - **DXF-4** (`b226ee4`) — flat patterns now carry through-feature circles via   a shared 3D-to-developed map; screen and DXF cannot disagree. [kernel-architect] - **DXF-5/T-16** (`cc35629`) — exported DXF declared metres on a millimetre   file; one document factory now sets MM explicitly, gated on emitted bytes. [kernel-architect] - **PICK-2** (`8384f1e`) — a bodyless tip feature no longer arms a PICKING   badge over zero targets; one shared guard refuses with a stated reason. [frontend-builder] - **FB-21** (`b505efe`) — the Z axis glyph pointed along kernel −Y from a   scene/kernel frame mismatch; both now derive through `occtToSceneTuple`. [frontend-builder] - **FB-9** (`92da971`) — verification only: already fixed by FB-7c, not   FB-21; gated end-to-end for the first time. [frontend-builder] - **NAME-2/T-21/T-8** (`c2700ee`) — edges had no tolerant durable tier   (faces had four); `resolve_edge_durable()` closes both orphaning cases;   the client-facing re-stamp chip filed separately as NAME-2b. [kernel-architect] - **EDGEFLANGE-1** (`3fba5fd`) — an edge flange could fold off a sheet's own   thickness edge and report Solved with no material to bend; candidates now   filtered to real sheet faces. [kernel-architect] - **MATE-1 kernel half GATED** (`287510f`) — locked three kernel-side   preconditions on S-15's fixture (0 bad of 14 offered faces); S-15's repro   is not kernel-side, ticket re-scoped to UI only (closed pass 15). [kernel-architect] - **REPICK-1/T-22** (`4c98ee0`, e2e fix `b036acd`) — re-picking a face used   to silently reset an authored hole placement to the new face's centroid;   now RE-ANCHORED (position preserved) unless never authored. [frontend-builder] - **SETTLE-2/SETTLE-3/CommandBand label-shedding** (`4fef60a`/`8b239e5`/   `ae1cea0`) — two SOLVE-1 regressions (a plain solve could re-orient a rigid   shape across its symmetry axis; a settle could sacrifice a circle's radius   pinning its centre) fixed and audit-verified; an unrelated e2e width-probe   break fixed by shedding command-band labels incrementally. [kernel-architect   + frontend-builder]

### SOLVE-1 CLOSED (groom pass 10, 2026-08-22, `7183955`, kernel-architect)

- **SOLVE-1** — AUDIT-PRODUCT R-5/R-5b/R-5c, P0 wrong geometry. An under-constrained solve now HOLDS the input geometry: `_GcsBuild.settle()` pins every free input coordinate back to the author's value after convergence, so a value edit no longer drags geometry the edit never named. A 245x performance regression in the rescued patch was found and fixed in the same commit. `docs/RESEARCH.md` §2/§9 corrected — the "guess-dependent by design" claim for under-constrained solves is now false, the determinism gate is sequence-level. SNAP-5 filed underneath it (line-by-line drawing never infers H/V).

### EXPORT-1/2 + REGISTER-1/2 + VIEWCUBE-1 + DXF-2a/2b/3 + DIM-3 + ESC-2 + VISION-FIX-1 CLOSED (groom pass 8, 2026-08-21) — the founder's 2026-08-17 file-page/export directive

Reconciled from `docs/AUDIT-ENGINEERING.md` Pass 7 M2: 10 of the prior 56 open Ready tickets were already shipped and the board didn't know (0/27 commits in range ticked ROADMAP/BACKLOG) — see DOCTICK-GATE for the fix.

- **EXPORT-1** (`3a7c4ca`) — export `ToolGroup` reachable with the Inspector collapsed. - **REGISTER-1** (`044f1f7`) / **REGISTER-2** (`e024daa`) — NAME column widened with ellipsis+title; default sort → last-worked descending, sticky header. - **VIEWCUBE-1** (`c28fbbc`) — cube renders at 1280×800/1366×768. - **DXF-2a** (`a915bf1`) / **DXF-2b** (`5bfb528`) / **DXF-3** (`fe72e4d`) — bend-table text off the BEND layer; profile-only flat-pattern export path; UTF-8-correct codepage (no more mojibake degree signs). - **EXPORT-2** (`1880db2`) — 3MF + glTF/GLB added to `ExportFormat`. - **DIM-3** (`71b04ef`) — Dimension's armed state gets a visible affordance surviving deselect. - **ESC-2** (`6fbeca0`) — Escape handling calls the single shared cascade (FB-13 landmine defused). - **VISION-FIX-1** (`6dfb597`, vision-steward) — Interop row retitled "(import + export)", assembly-import claim corrected. - Process debt, unchanged: none of the above independently code-reviewed.

### RECT-1 + SNAP-2 + SNAP-3 + MIRROR-1 CLOSED (groom pass 7, 2026-08-17) — vision-steward's 2026-08-16 competitive cluster

- **RECT-1** (`6d0f456`) — a rectangle drawn without typing a value is now a closed profile at placement (rigidity authored unconditionally), not 4 numerically-coincident but topologically disconnected lines. Filed RECT-2 (should drawing alone persist a sketch?). - **SNAP-2 + SNAP-3** (`c233a5b`, one mechanism) — a snap now carries the constraint address it took its coordinate from, so a grounded-looking corner no longer silently drifts on its first re-drive. Filed SNAP-4 (explicit Fix double-pinning an already-snap-grounded point → false OVER-CONSTRAINED). - **MIRROR-1** (`a0cc3f7`) — the mirror-axis picker now picks datum entities too, so a sketch's own centerline is a valid mirror axis. - None of the four independently code-reviewed — process debt.

### PICK-1 + GEOM-3 CLOSED (groom pass 6, 2026-08-16) — the two P0s pass 5 flagged as longest-waiting

- **PICK-1** (`2b266b1`) — a viewport pick now stamps the sub-shape's OWNING feature id, not the tip feature's, so a mid-tree fillet/shell/draft/hole/chamfer/edge-flange/hem can be re-picked for an edit. Not reviewed or QA'd at ship time. - **GEOM-3** (`1e39c14`, geometry-qa PASS `0628ceb`) — tier 4 face-signature gained 3 optional outer-wire invariants, fixing the >40%-open-area boss-deletion re-anchor case. The project's first `geometry-qa` pass (7154+10197+1176 differential comparisons, 1859 differences, all explained). Filed GQA-1 (P2, invariant triple not rotation-invariant), GQA-2 (P3), GQA-3 (P3, perf).

### QAH-1 CLOSED (2026-08-15 evening, `c3019b6`)

- **QAH-1** — e2e's "renders while orbiting" failure was the render-clock COLLECTOR, not the product: a mutation-test constant (`// MUTANT: always 0`) had been committed as product code while reconciling a stopped agent's work without running its own e2e gate. Fixed; a second independent defect (`waitForQuiet`'s 20s budget failing under load) fixed in the same commit. Not the same defect as `8d5be24`'s `cameraPose` race (kept apart correctly). - **Process lesson (kept — still applies to grooming):** the fix commit was an ANCESTOR of the groom pass's search range, so `git log <range>` found nothing and produced a confident, well-evidenced, WRONG "no commit touches this" conclusion. Re-deriving from git log is only as good as the window it searches; a truncated window makes "found nothing" look identical to "nothing to find." Caught by the orchestrator re-reading `git log` against the correct range.

### Groom passes 3-5 closures (2026-08-14/15, backlog-groomer) — c449235 review triage, DIM-1/QA7-1/GEOM-2/FB-19, the four founder 2026-08-01 sketcher reports

- **DIM-1** (`a810524`) — dimension VALUE field silently wrote wrong geometry (uncontrolled input, now ref-backed); gate band widened after ablation showed the original passing on a broken build ~1/3 of the time. - **SNAP-1** — founder "snap points not working" was NOT a snap-detection bug (measured correct in every buildable configuration); closed as a duplicate of SKETCH-2. - **SKETCH-2** (`5ceed6e`, follow-up `8f00dec`/`09cec01`) — origin/axes made selectable constraint targets via lazily-materialised pinned construction geometry; closed the blocking symmetric-about-a-datum-axis false-OVER-CONSTRAINED finding + QA-SK2-1 (fixture wasn't actually rigid) and QA-SK2-2 (modifier-click ordering). QA-SK2-3 and SNAP-2 filed separately. - SKETCH-1, VP-1, VP-1a — all QA'd green (`6df1170`); still never independently code-reviewed (flagged, not re-filed — same debt class as K8). - **Mutation/debug-marker CI gate** (`56297d2`, `scripts/check-mutation-markers.py`) — the grep-level guard QAH-1's root cause asked for; wired into `just lint` + CI. - **QA7-1** (`db144d7`) — the SEL-7 Create-costs-nothing wait was vacuous and its two comparison arms sampled at different settle depths. QA7-1b (scanner gap) filed. - **GEOM-2** (`8b95dac`, reviewed `57711c4`) — tier 4 (`enclosing_face_match`) anchors a planar face's identity on its OUTER boundary, fixing the thickness-edit-orphans-holes case; review quantified the honest limit → GEOM-3 (P0), GEOM-4/GEOM-5 (smaller follow-ups). - **FB-19** (`f7c41d9`) — chrome density (`FieldRow`, label-beside-control primitive). Not reviewed/QA'd/screenshotted at ship time — tracked as FB-19b. - **QA-VERIFY-1 CLOSED** — both specs it asked to verify (`sketch-orbit.spec.ts`, `sketch-reopen.spec.ts`) now run green. - **SKETCH-1** (`30a9f3f`) — a saved sketch re-opens via `beginEdit` hydration; QA'd green, never code-reviewed. - **VP-1** (`43c703c`) — orbit while sketching on the middle button; QA'd green (`sketch-orbit.spec.ts` 7/7), never code-reviewed. Fragile mechanism noted, not filed: it relies on r3f REPLACING rather than merging the `mouseButtons` prop — watch on any r3f/drei version bump. - **VP-1a** (`32e5b87`) — Alt(Option)+left-drag orbit reaches trackpads; never code-reviewed. Follow-ups filed: VP-1b (undiscoverable gesture), QAH-1 (above). - **c449235** (Dimension verb arms instead of dead-ending) — reviewed (`d6fc92b`, corrected two integration errors). Follow-ups filed: DIM-1, DIM-3, ESC-2, ESC-3.

### Backlog hygiene sweep (2026-08-14, backlog-groomer) — 104 shipped-but-unarchived items collapsed from a 2,850-line Ready

- **FB-20 (camera stolen after extrude)** — fixed 2026-08-14 (`d091112`);   UNREVIEWED (K8) — no independent code review or QA pass yet. - **CI-3 (gateway 502 on dropped keep-alive)** — fixed 2026-08-14 (`a2bb859`);   UNREVIEWED (K8) — no independent review or QA pass yet. - SPEC-4 — sketch-visibility's ink census measured by coverage, not exact   token. CLOSED-PENDING-QA, no independent QA pass yet. - SEL-7 — hole placement withholds its overlay from a hidden placement body. - SEL-4 — armed edge/shell/draft picks got the shared raycast hit-test. - CI-1 — sketch-visibility gate given a CI run + separation floor. - FB-1/1b — extrude/sketch-on-face stopped "flipping to xy" / not drawing. - FB-2 — a sketch line selects reliably. - FB-3 — face picking hit-test widened. - FB-4 — a cut extrudes into material, not away from it. - FB-5 — hovering a face offers "sketch on this face". - FB-6 — sketch ink visible on the face it sits on. - FB-7 — editor panels dock into a movable rail. - FB-10 — drawings dimension edge-to-edge (shell wall thickness). - FB-11 — the app states its build/version. - FB-12 — a 5px click drift no longer silently discards the pick. - FB-13 — Escape with nothing selected no longer ends the sketch. - FB-14 — a plain click replaces the pick set instead of accumulating. - FB-15 — draw tools support click-and-drag, not just click-then-click. - FB-16 — dimensions typed inline while drawing. - FB-17 — browser e2e suite gained gates for the founder's defect class. - FB-22 — a sketch origin/frame marker, snappable, on the sheet. - FB-23 — sketch-local undo/redo stack. - CONC-1..4, CONC-6 — session affinity, admission control, geometry-service   timeout honesty, rebuild-cache sizing, prefetch head-start — all shipped. - LIC-1..5 (incl. duplicate LIC-4 id) — GPL/LGPL/GCC-runtime licence hygiene,   bundled-binary scanning, `pnpm --port` footgun — all closed. - PERF-1, PERF-1b, PERF-2..5b — rebuild cache, mid-tree edit cost, validity   gate cost, STEP-import DoS bound, mesh compression, glTF fusion, per-face   provenance — all shipped (`docs/PERF.md`). - OPS-1 — backup, restore, restore test. - Audit N4 tail — exported STEP/drawing filenames carry the document name. - #58 — Settings surface, every row wired. - #WS1, #WS2 — workspace search/sort/rename/duplicate/delete + folders. - F3, F4 — feature-delete dependency warning; keyboard-shortcut help. - Assembly panel mass rollup (stopped promising a mass with no material). - QA-1/CM-6, QA-2, QA-3, QA-4, QA-4b — mirror validity, thickness-edit hole   destruction, dimension-survives-revision, lost-dimension-on-print (both   screen and export) — all fixed. - #57, #57b — mass properties (kernel + wire + UI gating on material). - UI-W1, UI-W2, UI-W3+W4, UI-W5 — timeline strip, per-instance visibility/   isolate, pre-selection + pinned references, entity snapping. - UI-REVIEW 2026-07-30 P1/P2/P3 — export-strip fold, timeline redundancy   claims, three silent gates. - CM-1..4 — mirror-erases-cut, pattern-of-cut no-op, cut-removes-nothing,   composed-body STEP topology — all fixed; friendly `cut_removed_nothing`   copy shipped. CM-5 (body-scope mirror after a revolve/sweep/loft cut   silently filled the void) fixed the same week, same class. - Mirror v2 — mirror a selected set of features (web authoring included). - "Is broken" register state, `eval_state` column, F2 staleness, J3/J3b   rollback-prefix verdict scoping, J2+N3+F2-frontend, sheet-number identity —   all shipped 2026-07-30/31. - Composition-matrix gate, jsdom component-test tier — structural test-gap   closures from the production-readiness assessment. - Assembly STEP export (AP214 product structure), E1a/E1b (section views wire   + web authoring), assembly interference/collision detection (+ false-   negative fix + unresolved-clash panel surface), assembly STEP import   (product structure, `body_step` dedup, permanent 3-service integration   test) — the "assembly is a one-way street" gap closed 2026-07-23/25. - Dedicated Hole feature slices 1 + 2 (geometry + web, counterbore/   countersink), feature suppress, mirror feature (kernel), gateway E2   (assembly export/interference web wiring), revolve construction-centerline   axis (kernel + web), datum editor midplane face-sides. - 2026-07-24 hard-audit P0/P2 batches, FINDINGS #6/7/8/9/10/15/21 — command   band, tooltips, live extrude-preview ghost, feature-localized selection,   right-click context menus, drawings/HLR burn-down, assembly STEP PRODUCT   naming, register template-feel fixes.

### Recently shipped — 2026-07-19 to 2026-08-11 (SEL-4/6/6b + CI-4 fixes, sketcher rework, drawings/assembly FINDINGS burn-down, sheet-metal v2, engineering-audit H/G findings)

Full narrative: `docs/CHANGELOG.md` §§"2026-08-08 to 2026-08-11", "2026-07-22 to 2026-08-01", "2026-07-19 to 2026-07-20", "2026-07-12". Items already one-lined in the hygiene-sweep entry above are not repeated here.

- SEL-4 (5 sub-slices) / SEL-6 / SEL-6b — one shared pick hit-test + hidden-body occlusion for every viewport verb (fillet/chamfer/measure/shell/draft/drill-anywhere/mates); independent QA PASS both times. - CI-4 fixes — `--fail-on-flaky` guard hardened (backend-builder); `waitForRenders` r3f-render counter (frontend-builder); `sketch-visibility` AA-phase flake identified, not a regression (SPEC-4). - FB-13/FB-14 — Escape no longer ends a sketch; plain click replaces the pick set (cascade unwinds one step at a time). - QA3-1..6 — drill-anywhere-on-a-face (stated numeric frame, live material check, concentric snaps); NEMA-17 imported-STEP dogfooding pass found 2 P1s (cannot drill where you want; a sketch on an imported face has no reference to the import). - **GATE-2** — a `.dockerignore` allow-list lost an entry (LIC-2 added a COPY source with no negation) and silently failed all 3 image builds, caught only by the slowest workflow; `scripts/check-build-context.py` re-implements moby's ignore-matcher to gate the whole class in `just lint`+CI. - **#42/SH-1** — shelling a rib at exactly 2x the wall thickness left a zero-width slit and reported `ok`; now a typed `shell_thickness_too_large` via one shared predicate; knife-edge proved 1.999/**2.000**/2.001. - **#31** — compose's projection-keyed anchors now refuse a repeated projection instead of silently dropping a view. - N1/N2 (frontend, kernel) — a widened/resized part re-anchors its dimensions and iso views instead of dying/overlapping; layout-issues check strip + RE-ANCHORED badge + a typed reason beside an unresolved dimension. - CONC-1/2/3 — gateway session affinity, bounded admission queue, honest 504-not-502 timeout (`docs/OPERATIONS.md` §6). - GATE-1 — full Playwright suite on every push, sharded 4 ways with a coverage-reconcile job. - OBS-1 — Prometheus `/metrics` for all 3 services, fail-closed outside dev (`docs/OBSERVABILITY.md`). - N8/N4/#50/N5 (kernel) — assembly STEP now instances parts instead of deep-copying geometry (21 instances: 504KB→58KB); exports named after the document; tapped-hole callout reaches every export format; exported page background is white not grey. - Mirror feature (kernel `MirrorFeature`/`MirrorParamsV1`, plane or datum axis) + web authoring — end to end. - Assembly import response-amplification DoS closed — occurrence-count + total-byte caps, typed 422s. - Assembly STEP import slices 1/2a (kernel) — XCAF reader hardened, CPU-bounded subprocess, editable single-body ingestion. - Section views E1a — end-to-end wire (kernel); E1b (web authoring) landed later, both listed in the hygiene sweep above. - Drawings D1-D4 — title-block author/date/notes, authored dimension placement honored, first-angle projection, assembly-view typed-422 (was an opaque 404); dead-capability sweep found 6 orphaned drawing capabilities total. - Drawings note-render, DE-4 artifact cache, sheet-size picker (A4→A0+ANSI), MB-4c per-body lump count, raster e2e hardening (root cause: a stale pre-units-convention format string, not raster drift — only 1 real ≤2px band-fit tolerance found). - Sheet metal WF-1/PB-1 (founder dogfooding) — cut-after-fold fold-back invariant, edge-flange width extents + auto bend-end relief + partial-width flat pattern; hem-on-a-flange-top now flat-patterns (TB-1 dogfooding); width-extents editor UI; corner-relief in-scene highlight. - Sheet metal v2 #1/#2 + spike (kernel) — non-parallel depth-1 bend stars (2D plus/cross layout), depth-≥2 bend-tree unfold (box corner/return/Z, self-overlap typed-rejected), tractability spike proved TRACTABLE via recursive tree walk. - STEP parse-timeout hardened — CPU-time `RLIMIT_CPU` ceiling + wall-clock liveness backstop, closes a CPU-contention flake without weakening the DoS guard. - Regression A/B (code review) — resilient face re-match no longer silently moves the resolved plane origin on a tier-2 (coplanar) match; cut-aware mirror no longer silently no-ops a reflected removal that misses the body (falls back to `mirror_union`, which already carries the body's own cuts). - H2/H3/H4/H5/CR-6 (AUDIT-ENGINEERING) — a sheet can no longer mix source documents/scales across views (typed 422s both layers); duplicate view-projection now unique-constrained at the DB; per-face provenance made opt-in + a linear spatial-hash matcher (was quadratic, 8.83s→1.82s at 4800 faces); sheets-per-drawing N+1 query fixed (3/sheet → 4 total); multi-sheet export filenames now name the sheet. - FINDINGS #1/#2/#3/#3-fe/#9/#11/#12/#13/#16/#17/#18/#19/#20/#22/#23 — cut-aware pattern+mirror (silent-wrong-geometry pair), same-face reference resilience + re-pick repair affordance, per-face provenance enabler, undo bypassing cross-doc protection, negative-diameter guard, Esc/dimension-hint/per-feature-error-copy UX trio, unit-aware property readouts, multi-sheet drawings UI (+ drag-to-place, per-sheet compose/export), viewport interaction polish (topology-as-translucent-patch, NavCue, per-instance contact shadows), jargon/ergonomics pass, "New part" navigates into it. - Audit G1/G2/G3/G4 — geometry S3 creds anchor-sourced from MinIO's; per-request work bounds (deflection/pattern/feature/instance/mate/interference/view/sketch/loft/selector caps) as typed 422s; compose port/credential hygiene; `scripts/check-compose.py` invariant guard. - Fail-closed on default datastore credentials (publishing blocker) — a publicly-known default/blank DB/queue/object-store password now refuses to boot outside `LOFT_ENV=dev`, one inherited `model_validator` across all 3 services. - Revolve construction-centerline axis (opens a half-profile); assembly interference/collision detection (N² pairwise `BRepAlgoAPI_Common`, typed never-500); assembly STEP export (AP214 product structure, byte-deterministic); drawings incumbent-parity matrix (12-item ordered campaign, WB-64-sourced).

### Phase 0/1/2 (through commit `a1c42be`) — scaffold through parametric core convergence

Full evidence: `docs/CHANGELOG.md`.

- Phase 0 — monorepo scaffold, py-kit bootstrap, service skeletons + compose, contract pipeline, web shell + first light, CI pipeline, geometry golden harness, community surface. - Phase 1 — STEP/STL export, feature-tree persistence, sketch solver + UI, extrude, viewport rendering, fillet/chamfer, full-flow e2e gate. - Phase 2 — topological naming design, construction geometry, tangent/perpendicular/parallel/equal/symmetric/concentric constraints, revolve, measurement, pattern; fillet/chamfer UI, trim/extend/offset/mirror, splines v1, sweep, loft; offset/datum planes, multi-loop closed profiles → holes; sketch-on-face, click-specific edge selection, shell, draft (**Part modeling ➖→✅**); STEP import v1 kernel-side; STEP import P1 security + gateway upload + UI picker (**Interop ❌→➖**); typed over-constraint diagnosis (#6); sketch dimension expressions (driving/driven); constrainable spline fit points v1.1 (**Sketching ➖→✅**); gateway auth-gate on geometry-compute routes (audit F7 P1 security); assemblies architecture decision endorsed.

### Phase 3-4b (through `a6a5814`, 2026-07-15 to 2026-07-19)

Full evidence: `docs/CHANGELOG.md`.

- Assemblies v1 — document model, `AssemblySolver` (numpy-only, no GPL), mate-geometry resolution, evaluation + shared-mesh tessellation, mate authoring UI, flat BOM (**❌→➖**). - Drawings v1 — document model, exact-HLR projection, dimension measurement/provenance + authoring, SVG export (**❌→➖**); export DE-0…DE-3 — server-composed placement, PDF/DXF serializers. - Multi-body modeling + booleans v1 (MB-0…MB-4c) — union/subtract/intersect between independently-built bodies, downstream fillet on a boolean-created edge, multi-lump bodies, multi-solid STEP import, guided `boolean_disjoint` recovery. - Sheet metal v1 — base flange, edge flange (+ provenance), depth-1-bend-star unfold, flat-pattern drawing view + bend table (**❌→➖**). - Performance benchmark suite + CI tripwires — two-tier gate (generous asserted ceilings + an opt-in median/p95 human-watched tier); infra half of the Performance ❌ row only, no ❌→➖ flip (the real-part corpus stayed open). - Units (length) v1; Undo/redo v1 (server-side bounded snapshot rings, verbatim id-preserving restore); Viewport makeover batches 1-3 (full-bleed canvas + atmosphere + matcap shading, decorative-chrome deletion, in-command depth/hover feedback); Datum-plane completeness (midplane + offset-chaining kinds); mesh-store MinIO/S3 swap, STEP re-parse cache, Redis-backed rate limiting.
