# Frontend redesign roadmap

**The source of truth for `loft-frontend-redesign-loop`.** Its Cost phase reads
this file and selects the next wave from it; its Evidence phase writes the
outcome back. A wave that does not update this file makes the next planner
re-derive everything, which is how the direction layer went dead here before.

**Founder directive, 2026-09-11 (verbatim):** *"The front end must be improved
for user experience. The flow of creating a part should be seamless. Also I want
to give full freedom of improving the UI design and flow. Changes are encouraged
to feel more like Fusion 360 or Plasticity."*

---

## Provenance, and the one methodological flaw you must know about

Two audits, run in parallel, **deliberately not coordinating** — the same
independence rule `product-auditor` and `engineering-auditor` follow. Where they
converge, that convergence is evidence; where they disagree, this file resolves
it in the open rather than splitting the difference.

| Audit | Lens | Doc | Evidence |
|---|---|---|---|
| Flow | what the journey costs the hand | `AUDIT-FLOW-2026-09.md` | `docs/screenshots/audit-flow-2026-09/` (11) |
| Craft | whether it feels like a modeling tool | `AUDIT-CRAFT-2026-09.md` | `docs/design/screenshots/craft-2026-09/` (16) |

**THE FLAW: THEY MEASURED DIFFERENT TREES.** Craft audited `f00fbe9`, the tip of
`claude/branch-review-development-hkbbnb`. Flow audited this branch, which is
main-based and **11 commits behind** — and four of those eleven touch the sketch
and viewport surfaces inside its lens. That is a real defect in how the pass was
dispatched (mine), and the honest response is not to average the two but to
re-check each flow finding against the eleven commits before it earns a row here.

Re-checked so far, on `f00fbe9` itself:

| Finding | Status on the dev tip | How it was checked |
|---|---|---|
| **F-1** first keystroke lost | **REPRODUCED, and the audit's MECHANISM was wrong** — see below | Re-measured by its builder on the merged tree: 0/30/60/**120** ms all lose the keystrokes, a WIDER band than the audit's (it had 120 ms surviving), because the audit timed from the pointer RELEASE while `placeAt` fires on the PRESS. FIXED in `2a90a92`. |
| **F-2** exits destroy an unsaved sketch | **CONFIRMED** | No navigation guard of any kind exists: `beforeunload`, `onbeforeunload`, `useBlocker`, `unstable_useBlocker`, `usePrompt`, `useNavigationBlocker` → **0 files**, against a positive control of `useNavigate` → 5 files. |
| **F-4** the five most-used verbs have no key | **CONFIRMED** | `PART_CREATE_SHORTCUTS` on the dev tip binds P/S/L/H/D/O/I — Pattern, Sweep, Loft, Shell, Draft, Hole, Mirror. Sketch, Extrude, Revolve, Fillet and Chamfer are absent. |
**WHAT F-1 SETTLED ABOUT THE AUDITS THEMSELVES, which is worth more than the fix.**
The audit said the cells "render `data-state="armed"` and say *Type a size*
**immediately**, but the window keydown listener attaches in a React effect that
has not committed yet." The symptom was exactly right and the mechanism was not.
An in-page probe at the moment the keys land:

```
pointerdown (shape placed, store draft set)      t+0.0 ms
keydown "1"  — cell in DOM: NO, state: "live"    t+26.7 ms
React commits the armed strip, listener attaches t+101.7 ms
```

The cells are **not in the DOM at all** — the strip is still showing its
read-only `live` readout. That kills the audit's own first proposal (focus the
width cell in the commit that places the shape: there is no such commit), and it
would have cost a builder a wave to discover if the brief had handed the
mechanism over as fact rather than as a claim to re-measure.

So the calibration for the rest of this table: **these audits are reliable about
WHAT IS BROKEN and are evidence, not fact, about WHY.** Every remaining row keeps
its "reproduce first" instruction for that reason, and a builder who finds a
different cause should say so loudly rather than fitting the fix to the ticket.

| F-3, F-5, F-6, F-7..F-11 | **unverified on the dev tip** | Each builder's first step is to reproduce on current code. A finding that has silently been fixed is a wave item that must be dropped, not built. |

---

## The measurement this loop steers by

`python3 scripts/check-flow-cost.py` reads `apps/web/e2e/` as a transcript of
real gestures. **The canonical register → part → sketch → extrude → edit →
export journey costs 30 gestures**, and it reads 30 on *both* trees, so the
number is not an artefact of the stale base.

Read that script's docstring before quoting it. It models an EXPERT who already
knows every verb; it is blind to hesitation and ambiguity (F-2 costs zero
gestures and is a P0); and it is gamed by editing the spec instead of the app.
**A drop is a question, never an achievement.**

The audits' own instrument is complementary and better at what this one cannot
see — clicks / keystrokes / mode switches / **hunts**, hand-counted:

| Part | clicks | keys | mode switches | hunts |
|---|---:|---:|---:|---:|
| Plate + 2 holes + fillet | 15 | 19 | 9 | **5** |
| …with the holes where they were clicked | 21 | 28 | 9 | **7** |
| Revolve + profile edit + rebuild | 11 | 19 | 9 | **3** |

**8 of those 15 hunts are ONE transition** — a solved sketch proposes nothing.

---

## Where the two audits independently converged

Convergence between auditors who never spoke is the strongest signal in this
document, and all three of these outrank anything either found alone.

1. **The app does not act on what you have just done.** Craft found that
   clicking geometry selects nothing that survives the pointer moving (P0-2);
   Flow found that a solved sketch proposes nothing and that this single gap is
   8 of 15 hunts (F-3). These are two ends of one root cause: **there is no
   held state for a next step to be next from**, so every command must be modal
   and the mandate's first flow test is unsatisfiable. Neither auditor saw the
   other's half. This is the spine of the roadmap.
2. **The same five things are already good and must not be rebuilt.** Both
   name the extrude drag handle, the rebuild-failure surface (named cause, last
   good body still on screen, `role="alert"`), and dimension-typed-at-creation
   as at or near the bar. Craft adds the modal tool bands and the token system;
   Flow adds the revolve editor (*"one keystroke to a correct feature — better
   than Fusion here"*) and feature-delete-with-dependents.
3. **The chrome is the distinctive part; the viewport is the generic part.**
   Craft measured it (7 hex literals repo-wide, 4 in comments, zero duplicated
   between DOM and WebGL; 80/80 interactive elements named; mandate 3a(c)
   passes outright). Flow corroborated from the other side — its P0s and P1s are
   all in behaviour, none in the chrome's appearance. **Spending this redesign
   on restyling panels would move the needle backwards.**

## Where they disagreed, and how it is resolved

| Question | Craft | Flow | Resolution |
|---|---|---|---|
| What goes first? | viewport realism — "the scene looks like CAD", cheapest visible delta | the two P0s — the app loses work | **Flow wins outright.** A tool that silently discards a typed dimension and destroys an unsaved sketch has no business getting prettier first. Craft's wave is cheap, parallel and viewport-only, so it runs *alongside* W0 rather than after it — it contends for nothing W0 touches. |
| Proposals or handles next? | handles — 86 % of parameters are form-only | proposals — 8 of 15 hunts are one transition | **Proposals first (W2), handles second (W3).** Both are right; the tiebreak is measured cost per unit of work. The proposal chip reuses `sketch-proposal-layer`, which already exists, and removes the single largest measured cost in the audit. The handle work needs a new `<ParametricGauge>` primitive first, and a primitive is a foundation item that takes a whole wave to itself. |
| Is the editor panel a defect? | yes — 17 identical stacked forms, 550 px from the geometry (P1-3) | not raised; the editors were judged workable | **Craft wins, but late (W5).** Flow did not contradict it, it simply measured cost and the panel is cheap *once you know where it is*. That is the expert-model blind spot in the gesture metric, stated in its own docstring. Note `4009042` (one of the eleven) already made all seventeen say why they are grey, so the surface is actively improving — re-audit before rebuilding it. |

---

## The waves

Every item names ONE subtree. Items marked **⚑ foundation** claim
`packages/design/**`, `apps/web/src/store/**` or `apps/web/src/lib/**`; the loop
builds at most one of those per wave, first and alone, and the rest of the wave
starts from its commit.

### W0 — stop losing the user's work *(blocks everything; not a design wave)*

Neither item is a matter of taste, and both fail the mandate's *"never a silent
wrong model"* rule outright.

| id | title | subtree | proven by |
|---|---|---|---|
| **FLOW-A1** ✅ **LANDED `2a90a92`** | The first keystroke after a draw always lands. The window listener no longer depends on a RENDER — it reads the draft live from the store, which `placeAt` sets synchronously in the pointer handler — and keys arriving before the cells exist are buffered and replayed in the cells' REF CALLBACK (not a layout effect: drei's `<Html>` portals them in a commit of its own). | `apps/web/src/viewport/**` | `draw-dimension-arming.spec.ts`, 6 cases queued on ONE CDP socket with no await between press and keys. Mutation: all six red (`toHaveValue("100")` received `""` ×4, the strip never closed), restored 6 green. |
| **FLOW-A2** ✅ **LANDED `501331b`** | An unsaved sketch survives Back, the breadcrumb and reload — a guard, plus a per-part draft | `apps/web/src/routes/**` | e2e: draw 4 entities, navigate away by each of the three exits, return, and the entities are still there (or an explicit prompt was shown and honoured). |

### W1 — the scene looks like CAD *(viewport only, runs alongside W0)*

Touches no data model, no API and no editor, so it contends with nothing above.

| id | title | subtree | proven by |
|---|---|---|---|
| **CRAFT-1** ✅ **LANDED `57d3bf8`** | B-rep edge overlay derived from the face partition (`faceStarts`) — a fillet is tangent, so `EdgesGeometry` draws nothing | `apps/web/src/viewport/**` | Pixel: edge ink on the filleted plate is **0** today; assert > 2 000 px and that it does not collapse when a fillet is added. |
| **CRAFT-2** ✅ **LANDED `57d3bf8`** | The grid survives an axis-aligned orthographic camera | `apps/web/src/viewport/**` | Pixel: grid ink at front-ortho ≥ 50 % of front-perspective. Today 2 396 vs 7 514, and all 2 396 are the body's own antialiasing. |
| **CRAFT-4** | Cursor states over the viewport | `apps/web/src/viewport/**` | e2e: `getComputedStyle(canvas).cursor` changes off `auto` over a face, and reads `grab`/`grabbing` on a manipulator. |
| **CRAFT-3** ✅ **LANDED `57d3bf8`** | Origin triad visible by default, dimmed | `apps/web/src/viewport/**` | e2e: `origin-axis-{x,y,z}` ink present at rest. |
| **CRAFT-5** | Contact shadow + light AO | `apps/web/src/viewport/**` | Pixel: mean luminance in a 40 px band under the body is ≥ 15 % below the background gradient at that height. |
| **CRAFT-6** ✅ **LANDED `a340ff5`** | The CUBE persists in sketch and plane-pick modes; the projection control stays hidden | `apps/web/src/components/**` | e2e: `view-cube` has a non-zero box in all three modes at 1280×800, and `view-projection` remains absent while authoring. **Split deliberately — see the note below.** |

**CRAFT-6 is not what the audit thought, and the difference matters.** Checked
on the merged tree: `Viewport.tsx:1357-1358` unmounts BOTH the cube and the view
rail with `viewNav`, which `PartPage.tsx` sets to `mode === "off"` — so they go
during sketch and plane-pick, exactly as reported. But this is not an oversight;
the code argues for it, in a comment written by whoever built the sketch rig:
*"the view rail and the cube unmount with `viewNav`, so the projection control
is not on screen during authoring"*, because the sketch rig holds perspective by
parking the camera at a computed distance, which a parallel camera does not
answer to.

Half of that reasoning is right and half is not. Hiding the PROJECTION control
during authoring is correct — it would offer a mode the sketch rig cannot honour.
Hiding the CUBE is not: orientation matters MORE while you are drawing on a
plane in space, not less, and the cube is an orientation readout before it is a
control. So the item is split rather than overruled, and a builder who reads the
comment will not have to choose between the roadmap and the code. If honouring a
cube facet click during sketch mode turns out to fight the rig, the cube may be
display-only there — say so and ship that.

### W2 — the next step proposes itself *(the biggest measured win)*

| id | title | subtree | proven by |
|---|---|---|---|
| **FLOW-B1** ✅ **LANDED `78aaa67`** | The solve itself writes an "Extrude Sketch1 · ⏎" chip onto the profile, reusing `sketch-proposal-layer` | `apps/web/src/viewport/**` | e2e: solve a sketch, assert the chip exists with the profile pre-selected, press Enter, assert the extrude editor opens with that profile. Gesture cost of the plate journey drops by the hunt. |
| **FLOW-B2** ✅ **LANDED `d5e936a`** | `E`/`R`/`F`/`C`/`K` bound for Extrude, Revolve, Fillet, Chamfer, Sketch | `apps/web/src/shortcuts/**` | Unit: `PART_CREATE_SHORTCUTS` contains all five. e2e: each fires its editor under its stated condition. |
| **FLOW-B3** ✅ **LANDED `fb63809`+`6097448`** | One accented next-verb after a feature builds | `apps/web/src/components/**` | e2e: after an extrude completes, exactly one accented affordance is present and it is the likely next verb. |

### Where the programme actually stands (2026-09-13)

W0, W1 and W2 have landed. Three things are worth carrying forward, and two of
them are corrections to this document's own optimism.

**Every wave dispatched by hand needed a review pass, and each one found a
BLOCKING defect of the SAME class: two changes that are each correct and wrong
together.** W0's was a window listener whose only target guard was
`isTypingTarget`, so `Enter` on the new exit prompt applied a sketch dimension
instead of pressing the focused button — visible in the screenshot committed as
proof the feature worked. W2's was the identical mechanism on a different
surface, reached by pressing `?` to read the key card and then pressing the `E`
the card was displaying. Neither builder could have found its own: one predated
the other's surface, and the unit test asserting the opposite contract renders
its component in isolation. `lib/modalGate.ts` was written after W0 as the
general answer and then generalised to exactly one registrant, which is why W2
walked straight past it; it now carries an audit test that fails by name when a
new raw global key listener appears, and an alarm that fires when a key reaches
the workspace while an `[aria-modal="true"]` element is on screen.

**The flow-cost metric has NOT moved, and saying otherwise would be the easiest
lie available.** `scripts/check-flow-cost.py` still measures the canonical
journey — register → part → sketch → extrude → edit → export, the only one with
no API shortcuts — at **30 gestures**, exactly what it cost before W2. That is
not a measurement bug: `full-flow.spec.ts` was never touched, so the transcript
still walks to the toolbar. W2 made a shorter path EXIST; nothing made it the
path the journey takes. Until a journey exercises the chip and the accelerators,
the honest claim is "we shipped shortcuts", not "creating a part got cheaper"
(filed as `FLOW-JOURNEY-GAP-1`).

**W1 measured two audit hypotheses and found the mechanisms were different and
stronger than proposed.** The audit thought the missing ortho grid was a
`fadeDistance` tuning problem; it is geometric — under a parallel projection a
plane containing the view direction projects to a LINE, so no fade setting could
ever have rescued it, which is also why iso-ortho always looked fine. And the
missing edges on a filleted body were not a threshold to tune but a category
error: `EdgesGeometry` is a mesh CREASE detector and a fillet is tangent by
construction. Both are worth remembering when reading the remaining audit rows —
this document's "likely cause" column is a hypothesis, not a finding.

### W3 — the numbers have handles ⚑

CRAFT-8 is this wave's foundation item and therefore lands first and alone: the
four gauges after it are all the same primitive applied to different verbs, so
building any of them before it exists means building it four times and reviewing
four dialects of one control. That is the whole argument for the loop's System
phase, arriving in its most literal form.

| id | title | subtree | proven by |
|---|---|---|---|
| **CRAFT-8** ⚑ | Extract `<ParametricGauge>` (anchor, axis, value, setter, unit, snap ladder) from `ExtrudeDragHandle` | `packages/design/**` | Pure refactor: extrude re-expressed through it, existing e2e green, screenshot match — a refactor must not move a pixel. |
| **CRAFT-7** | Fix the extrude grip: hit region = the drawn arrow; the on-geometry tag becomes an input | `apps/web/src/viewport/**` | e2e: `elementFromPoint` down the gauge axis resolves to `extrude-depth-handle` at ≥ 8 of 12 offsets (today 3 of 15); a real `page.mouse.click` on the arrowhead changes the distance. |
| **CRAFT-9** | Linear gauges: fillet radius, chamfer distance, shell thickness, hole depth + Ø, datum offset | `apps/web/src/viewport/**` | e2e per verb: drag N px, the editor field changes AND the ghost redraws; arrow keys step the same value. |
| **CRAFT-10** | Angular gauges: revolve angle, draft angle, bend angle | `apps/web/src/viewport/**` | e2e on `revolve-angle` / `draft-angle`. |
| **CRAFT-11** | Pattern gauge: drag to set spacing, drag past a pitch to add count | `apps/web/src/viewport/**` | e2e: drag changes `pattern-spacing`; past the pitch increments `pattern-count`. |

### W4 — select, then act ⚑ *(the structural one; the convergence item)*

| id | title | subtree | proven by |
|---|---|---|---|
| **CRAFT-12** ⚑ | Persistent geometry selection — `ModelMesh` gains `onClick` → a selection store; Shift adds, Esc clears | `apps/web/src/store/**` | e2e + pixel: click a face, move the pointer 300 px away, the tint persists. `14-click-selects-nothing.png` is the before frame. |
| **CRAFT-13** | Selection readout, with hover and selected actually distinguishable | `apps/web/src/components/**` | Pixel: selected chroma exceeds hovered by ≥ 30 %. Today 53.6 vs 53.4. |
| **CRAFT-14** | Pre-selection seeds commands — pick edges, press F, the fillet opens with them | `apps/web/src/features/**` | e2e: select two edges, open Fillet, `fillet-edges` = 2 and Create is reachable with zero further picks. |
| **FLOW-C1** | A face click seeds the hole point (`setHolePointPicked` already takes a point) | `apps/web/src/routes/**` | e2e: click a face once; the hole lands where clicked, not at the face centre. Today two clicks at the same pixel give `(50, 25, 20)` then `(35.6, 28)`. |
| **FLOW-C2** ⚑ | `lastFeatureDefaults` — consecutive identical features carry their settings | `apps/web/src/store/**` | e2e: hole 1 at Ø8 through-all; hole 2 opens at Ø8, not the Ø6 default. **Conflicts with CRAFT-12 for `store/**` — schedule in separate waves.** |

### W5 — the editor is a tag on the work, and the chrome repairs

`CRAFT-15`, `CRAFT-16` (tag-on-geometry editors), `CRAFT-17` ⚑ (tracking scale
+ gate), `CRAFT-18` (labels ≥ 1600 px), `CRAFT-19` (`timeline-stop` /
`rollback-slot` box collision), `CRAFT-20` (STATUS above the fold),
`CRAFT-21` (Home restores projection; ViewCube re-fits), `CRAFT-22` (one export
address), `FLOW-C3` ⚑ (Tab order), `FLOW-D*` (fillet opens on "pick edges";
dimension glyphs look editable; the nav cue retires itself).

---

## What the roadmap assumes exists, checked on `f00fbe9`

Three items say "reuse what is already there", which is only a cheap plan if it
is true. Verified rather than assumed:

| Claim | Found at |
|---|---|
| `sketch-proposal-layer` to hang FLOW-B1's chip on | `apps/web/src/viewport/SketchProposal.tsx:261` — **note it is in `viewport/`, not `sketch/`**, which is why FLOW-B1's territory is `viewport/**` |
| `ExtrudeDragHandle` for CRAFT-8 to generalise | `apps/web/src/viewport/ExtrudeDragHandle.tsx` |
| `setHolePointPicked` already taking a point, for FLOW-C1 | `apps/web/src/routes/PartPage.tsx:661,4022` |

## Scheduling constraints the planner must respect

- **One foundation per wave.** `packages/design/**`, `store/**` and `lib/**` are
  claimable but never in parallel. CRAFT-8, CRAFT-12, CRAFT-17 and FLOW-C2 are
  each a wave's solo item.
- **CRAFT-12 and FLOW-C2 both want `store/**`.** Separate waves. CRAFT-12 first:
  FLOW-C2 is a convenience, CRAFT-12 unlocks W4 entirely.
- **`test/`, `router.tsx`, `main.tsx`, `index.css` are unclaimable.** Work
  needing them belongs inside the item that needs it.
- **Every builder reproduces its finding on the current tree first.** Half of
  these were measured 11 commits back. A finding already fixed is an item to
  drop, and dropping it is a good outcome, not a wasted wave.

## Explicitly NOT proposed

Both audits independently said so, and a roadmap that rebuilds working things is
worse than no roadmap:

- The **extrude drag handle** (fix its hit region, keep its design), the
  **revolve editor**, the **rebuild-failure surface**, **feature delete +
  dependents**, **dimension-typed-at-creation** as a concept, the **modal tool
  bands**, and the **token/palette system**.
- A new palette, a new type system, or a "modernisation" of the chrome.

---

## Changelog

- **2026-09-12** — W0 opened. FLOW-A1 landed (`2a90a92`); its finding that the
  audit's mechanism was wrong is recorded above and re-calibrates how the rest
  of the table should be read. FLOW-A2 in flight. CRAFT-6 split after reading
  the code's own justification. A follow-up is owed: FLOW-A1's builder flagged a
  THIRD address in the same dropped-keystroke family — `dimension-editor`'s cell
  is also inside a commit that trails the click which opens it — unmeasured, and
  in `routes/` territory so it could not check while a sibling held it.
- **2026-09-11** — created. Reconciles the flow and craft audits of the same
  day. No wave has run yet; every row is a proposal, not a commitment.
