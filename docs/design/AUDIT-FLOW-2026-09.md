# Flow audit — "the flow of creating a part must be seamless"

**Date:** 2026-09-11 · **Auditor:** frontend-qa (founder-directed, journey lens)
**Method:** real native stack (gateway :8060 / documents :8061 / geometry :8062,
SQLite, no containers), real Chromium at 1600×1000 driven by Playwright with
`handClick` (drift + dwell, not synthetic zero-travel clicks). Three parts
modelled end to end with a per-step instrumented ledger. Load average ranged 0.30–4.30 across the
pass (a sibling auditor's stack was live on :8070-8072/:5270 for part of it) —
wall-clock timings below are therefore indicative only; the COUNTS are not
load-sensitive, and the one timing-critical finding (F-1) was deliberately
re-measured in a quiet window and came back byte-identical.

**Tree under audit:** `d4552e3` (the shared checkout's HEAD,
`claude/frontend-workflow-redesign-8ae3su` == `main`). **Eleven commits on
`claude/branch-review-development-hkbbnb` postdate it** (tip `f00fbe9`,
2026-09-04 07:47) and several are flow-relevant — `745289e` SEL-2 sketch pick
naming, `f4273d3`/`4009042` editor gate reasons, `51962bf` command tint,
`f00fbe9` leaving a sketch restores the view. The checkout is SHARED with a live
sibling agent, so switching branches was not safe; **every finding below was
cross-checked against `git log -p d4552e3..f00fbe9` before filing**, and any
finding those commits already close is marked so.

**Scope boundary:** this is the JOURNEY. A sibling auditor is running
independently on visual craft and direct manipulation; where we agree, treat
the agreement as evidence, not as coordination.

---

## Verdict

**The flow architecture is right; two defects in it destroy or discard the
user's work, and one missing transition makes every feature cost a trip to the
toolbar.**

Three parts modelled end to end, all three geometrically correct
(100 × 50 × 20 plate; a revolved tube at 150,796.45 mm³ — π(30²−10²)·60 to
five figures; a parametric edit propagating cleanly). Per-part totals
(clicks / keys / mode switches / hunts): **plate 15 / 19 / 9 / 5** ·
**plate re-run with the holes placed properly 21 / 28 / 9 / 7** ·
**revolve 11 / 19 / 9 / 3**. (The second ledger re-does the plate, so the three
do not sum to a meaningful figure — read them per part.)

- **8 of the 15 recorded hunts are the same transition**: a solved sketch
  proposes nothing,
  so the eye and the hand travel to the toolbar for a verb the app already
  knows you want. The mandate names this exact case.
- **Two P0s**, neither reachable by the 2026-07-24 pass — F-1 lives in code
  that shipped after it, F-2 in a class of exit it never drove:
  keystrokes typed within ~100 ms of a draw are silently dropped and the part
  comes out the wrong size (F-1, reproduced identically at load 0.34 and at
  load 4.30); and three ordinary exits — browser Back, an in-app breadcrumb,
  a reload — destroy an unsaved sketch with no prompt and no recovery (F-2).
- Against that: FB-16 intent capture is real and Fusion-grade, the profile IS
  pre-selected, Escape is correct in four separate contexts, a viewport click
  does not destroy an open command, and a failed rebuild is as honest a surface
  as this product has. The revolve editor takes **one keystroke** from a solved
  profile to a correct feature, which is better than Fusion.

The cheapest large win is Wave 2: the proposal machinery
(`SketchProposal.tsx`) and contextual tool labelling (*"Repeat Extrude1"*)
already exist and are already proven — they are simply not wired to the one
transition that matters most.

**Verified against the newer tip:** none of the eleven commits in
`d4552e3..f00fbe9` touch the draw-dimension keystroke path, the shortcut
registry's command list, the hole face-pick point seeding, or any navigation
guard. Every finding below stands on the newest tree too.

---

## Instrumentation — what the four numbers mean

- **Clicks** — discrete pointer activations. A drag counts as one.
- **Keys** — keystrokes, counting each character of a typed number.
- **Mode switches** — the app's own mode changed (breadcrumb text changes, a
  command band replaces the toolbar, a tool arms).
- **Hunts** — the user's attention had to move to a *different screen zone*
  than the one they last acted in, **and the app did not direct them there**
  (no highlight, no autofocus, no proposal, no arming banner). A zone change
  the app proposed is not a hunt; that is the whole point of proposing. This
  is the operational definition used by the ledger
  (`apps/web/e2e/zzflow-ledger.ts`, written for this pass, not committed).

Fusion 360 comparisons below are **recalled from use, not measured** — they
are stated only where the gap is large enough that recall is safe.

---

## Part 1 — 100 × 50 × 20 plate, two through holes, one filleted edge

Measured ledger (`zzflow-part1.spec.ts`). Setup (register, name a part) is row 1
and is included because it is part of "creating a part."

| # | Step | Clicks | Keys | Mode switches | Hunts | Zone |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | Create part from the register (type name + Enter) | 1 | 6 | 1 | 0 | topbar |
| 2 | Click NEW SKETCH | 1 | 0 | 1 | 0 | toolbar |
| 3 | Pick the XY plane | 1 | 0 | 1 | 0 | toolbar |
| 4 | Press **R** for the rectangle tool | 0 | 1 | 1 | 0 | keyboard |
| 5 | Click two corners (drawn ≈80 × 40, not exact) | 2 | 0 | 0 | 0 | viewport |
| 6 | Type `100` Tab `50` Enter **into the cells at the cursor** | 0 | 7 | 0 | 0 | viewport |
| 7 | Click FINISH SKETCH | 1 | 0 | 1 | 0 | strip |
| 8 | Click EXTRUDE | 1 | 0 | 1 | **1** | toolbar |
| 9 | Type `20` into the autofocused distance, Enter | 0 | 3 | 0 | 0 | editor |
| 10 | Click HOLE | 1 | 0 | 1 | **1** | toolbar |
| 11 | Click the top face | 1 | 0 | 0 | 0 | viewport |
| 12 | Type diameter | 0 | 1 | 0 | 0 | editor |
| 13 | Click CREATE | 1 | 0 | 0 | 0 | editor |
| 14 | Click HOLE again (second hole) | 1 | 0 | 1 | **1** | toolbar |
| 15 | Click the top face again | 1 | 0 | 0 | 0 | viewport |
| 16 | Re-enter diameter + depth mode | 1 | 1 | 0 | **1** | editor |
| 17 | Click CREATE | 1 | 0 | 0 | 0 | editor |
| 18 | Click FILLET | 1 | 0 | 1 | **1** | toolbar |
| | **TOTAL** | **15** | **19** | **9** | **5** | |

Recalled Fusion 360 equivalent for the same part, **not measured**: roughly
9–11 clicks, ~14 keystrokes, and — the number that matters — **0–1 hunts**,
because after a solved sketch Fusion leaves the profile selected and the
next verb is either pre-armed or one keystroke (`E`) away, and because the
Hole command places the hole where you clicked.

### The part that came out was correct
`prop-extents` read `100 × 50 × 20 mm` and the sketch carried nine
auto-authored constraints (`C,C,C,C,H,H,V,V,C`) plus the two typed dimensions.
The modelling is sound; the cost is in the transitions.

### Part 1b — what the two holes and the fillet actually cost

Re-run with the hole placed where a user would want it
(`zzflow-part1b.spec.ts`). Row 1 folds in the plate from Part 1.

| # | Step | Clicks | Keys | Mode switches | Hunts |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | (setup) plate to 100 × 50 × 20 | 6 | 16 | 5 | 0 |
| 2 | Click HOLE | 1 | 0 | 1 | **1** |
| 3 | Click the top face **at the spot the hole should go** | 1 | 0 | 0 | 0 |
| 4 | Click CHANGE on the Point row to arm a **second** pick | 1 | 0 | 1 | **1** |
| 5 | Click the **same spot again** | 1 | 0 | 0 | **1** |
| 6 | Type X 20, Y 25, dia 8 (three fields, each needing focus) | 2 | 6 | 0 | **1** |
| 7 | CREATE | 1 | 0 | 0 | 0 |
| 8 | Click HOLE again | 1 | 0 | 1 | **1** |
| 9 | Re-do the whole hole — nothing carried over | 5 | 6 | 0 | **1** |
| 10 | CREATE | 1 | 0 | 0 | 0 |
| 11 | Click FILLET | 1 | 0 | 1 | **1** |
| | **TOTAL** | **21** | **28** | **9** | **7** |

## Part 2 — revolve, then change the profile and watch it rebuild

`zzflow-part2.spec.ts`. **This is the best flow in the product** and the
roadmap below deliberately does not touch it.

| # | Step | Clicks | Keys | Mode switches | Hunts |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Create part 'Spindle' | 1 | 8 | 1 | 0 |
| 2 | Click NEW SKETCH | 1 | 0 | 1 | 0 |
| 3 | Pick XZ | 1 | 0 | 1 | 0 |
| 4 | Press **R** | 0 | 1 | 1 | 0 |
| 5 | Draw the profile, type `20` Tab `40` Enter | 2 | 6 | 0 | 0 |
| 6 | Click FINISH SKETCH | 1 | 0 | 1 | 0 |
| 7 | Click REVOLVE | 1 | 0 | 1 | **1** |
| 8 | **Enter** — profile, axis and 360° were all already right | 0 | 1 | 0 | 0 |
| 9 | Click the Sketch row in the tree to edit the profile | 1 | 0 | 1 | **1** |
| 10 | Double-click the `40` dimension glyph | 2 | 0 | 1 | **1** |
| 11 | Type `60`, Enter | 0 | 3 | 0 | 0 |
| 12 | Click FINISH SKETCH — rebuild | 1 | 0 | 1 | 0 |
| | **TOTAL** | **11** | **19** | **9** | **3** |

Rebuild verified geometrically: the tube re-solved to **150,796.45 mm³** —
π(30² − 10²)·60 = 150,796.4, i.e. the parametric edit propagated exactly.
`eval-status` returned to `Solved`. Recalled Fusion equivalent: comparable
click count; Loft's step 8 (one keystroke for a fully-specified revolve) is
**better than Fusion**, which makes you pick an axis.

## Part 3 — the exit matrix (changing your mind)

Every exit driven for real; `zzflow-part3/exit/exit2.spec.ts`.

| Exit | Context | What happens | Verdict |
| --- | --- | --- | --- |
| **Esc** | mid rubber-band (first corner placed) | in-progress entity dropped, **tool stays armed**, 0 entities | ✅ exactly right |
| **Esc** | draw-time size cells armed | cells dismissed, **shape kept** (4 entities) | ✅ documented + correct |
| **Esc** | sketch mode, nothing armed | **nothing at all**, any number of times | ➖ parity with Fusion; silent no-op |
| **Esc** | editor open, focus INSIDE | editor closes, feature **not** created | ✅ |
| **Esc** | editor open, focus OUTSIDE the editor | editor closes, feature not created | ✅ **the 2026-07-24 P1 is CLOSED** |
| **click in the viewport** | editor open, `42` typed | editor **stays open**, value preserved, nothing created | ✅ |
| **browser BACK** | editor open with a typed value | navigates to the register, **no prompt**, command discarded | 🔴 |
| **browser BACK** | **sketch mode, 4 unsaved entities** | navigates away, **no prompt**, the sketch is **gone** | 🔴 **P0** |
| **in-app breadcrumb "Parts"** | sketch mode, 4 unsaved entities | navigates away, **no prompt**, the sketch is **gone** | 🔴 **P0** |
| **page reload** | sketch mode, 4 unsaved entities | no `beforeunload`, the sketch is **gone** | 🔴 **P0** |

After every one of the three destructive exits, returning to the part shows
`features: 0` and **no resume band, no recovery, no undo entry**. The
`ResumeBand` that exists is on the parts register and answers "which document
was I in", not "you were mid-sketch".

---

## What already works — do not rebuild any of this

The app is materially further along than a defect list suggests. Measured
this pass, all of it:

1. **FB-16 intent capture is REAL and it is good.** Drop a rectangle and the
   size cells appear **at the cursor** (rendered through `<Html>` at the
   gesture's end point, `SketchScene.tsx:1103`), reading `Type a size · Tab
   switches · Enter applies`. You type `100` Tab `50` Enter **with no click and
   no re-selection**, and nine auto-authored constraints
   (`C,C,C,C,H,H,V,V,C`) arrive with the rectangle so the profile is rigid
   before it is dimensioned. This is Fusion's gesture, and we have it.
   (One race defect against it — F-1 below.)
2. **The profile IS pre-selected.** With one sketch, `extrude-profile` is a
   read-only span reading `Sketch1`; with two, it is a `select` already set to
   one of them. The mandate's "with the profile pre-selected" half is done.
3. **The revolve editor is the best-argued surface in the product.** Opened on
   a solved profile it arrives with profile = `Sketch1`, axis =
   `Z axis · through the origin`, angle = `360` **autofocused** — and the axis
   dropdown offers *inferred* axes from the profile itself
   (`Horizontal · 20 mm · profile…`). One keystroke creates a correct revolve.
4. **A failed rebuild is loud and honest.** A 40 mm fillet on a 10 mm plate
   gives `eval-status: Failed`, an `ERR` row, and a `role="alert"`:
   *"This feature couldn't build — Fillet failed in the kernel (ValueError);
   the radius (40.0 mm) may be too large for an adjacent face."* — **while the
   last good body stays on screen with correct extents**
   (`60 × 40 × 10 mm`). No silent wrong model. Evidence:
   `docs/screenshots/audit-flow-2026-09/rebuild-failure.png`.
5. **Disabled tools state their reason in the DOM**, per tool, and the reason
   is *contextual*: `Draw a sketch to extrude`, `Create a body first`,
   `Needs two bodies`, `Add a base flange first`. (The 2026-07-24 clipping P2
   is the sibling auditor's ground; I am not re-reporting it.)
6. **The toolbar re-labels itself from history.** After `Extrude1`,
   `new-pattern` reads **"Repeat Extrude1"** and `new-mirror` reads
   **"Mirror Extrude1"**. That is a proposal mechanism already in the product.
7. **Re-entering a sketch is one click.** Clicking the sketch row in the
   feature tree drops straight into sketch mode (1.77 s measured), the
   dimension glyphs are live, and double-clicking one opens its editor.
8. **Clicking in the viewport does not destroy an open command** — the editor
   stays, the typed value survives.
9. **Extrude already has a drag handle.** `extrude-depth-handle`,
   `extrude-depth-readout` (`D 10 mm`) and `extrude-depth-steps`
   (*"Arrow keys step 0.5 mm; Shift or Page keys…"*) are all mounted. The
   mandate's "single biggest gap" is at least partly shipped; the sibling
   auditor owns judging how it feels.
10. **Per-feature delete exists** (`requestDeleteFeature` →
    `FeatureDeleteConfirm` with a dependents list) — the 2026-07-24 P2 is
    **closed**, though it lives in a row overflow menu rather than on the row.

---

## Findings

Severity: **P0** destroys work or produces a wrong result silently · **P1** the
flow test named fails and it costs real time every part · **P2** friction ·
**P3** polish. Each finding names the flow test from `CLAUDE.md` it fails.

### 🔴 P0 · F-1 — typing a size in the first ~100 ms after a draw is SILENTLY discarded, and the part is then simply the wrong size
**Fails:** *capture intent where it forms* · *never a silent wrong model*
**NEW.**

The draw-time cells render `data-state="armed"` and display *"Type a size · Tab
switches · Enter applies"* **immediately**, but the `window` keydown listener
that routes the first digit into them is installed in a React effect
(`SketchScene.tsx:1059-1068`) that has not committed yet. Measured by sweeping
the delay between the second corner click and the first keystroke
(`zzflow-race.spec.ts`, full `1`,`0`,`0`,Tab,`5`,`0`,Enter sequence each time):

| Delay after the corner click | width cell | height cell | dimension glyphs authored |
| ---: | --- | --- | --- |
| 0 ms | `""` | `""` | none |
| 0 ms (repeat) | `""` | `""` | none |
| 30 ms | `""` | `""` | none |
| 60 ms | `""` | `""` | none |
| 120 ms | `100` | `50` | `40,50` → `100,50` ✅ |
| 250 ms | `100` | `50` | ✅ |
| 500 ms | `100` | `50` | ✅ |

The whole sequence — six keystrokes and an Enter — vanishes. Nothing is
reported. The sketch then saves happily at the size it was *dragged* to, and I
hit this for real: the Part 1b plate came out **80 × 40 × 20 instead of
100 × 50 × 20** and the run only caught it because a spec asserted the extents.
A user gets a wrong part and a clean green UI.

This is DIM-1's family (`a810524`, dropped keystrokes in the dimension cell)
at a second address. Load average was 4.30 when the boundary was measured, so
the 60/120 ms figure is not exact — but the failure at 0 ms reproduced on every
attempt across three separate runs at loads from 0.9 to 4.3.

**System-level fix:** the cells must not advertise readiness they do not have.
Either focus the width cell synchronously in the same commit that places the
shape (so the browser delivers the digit with no listener in the path), or
buffer keystrokes from the moment `armed` becomes true and replay them when the
listener attaches. The `data-state` attribute already distinguishes
`live`/`armed`; a third state is not needed, the two must just be *true*.
**Assertion that would prove it:** place a rectangle and press a digit with
**zero** intervening round trips; `draw-dimension-width` must read that digit.

### 🔴 P0 · F-2 — three ordinary exits destroy an unsaved sketch with no prompt and no recovery
**Fails:** *no dead ends, no ambiguous exits* · *Escape never silently destroys work*
**NEW** (the 2026-07-24 pass audited Escape, not navigation).

With four entities drawn and not yet saved:

- **browser Back** → register page, no dialog, sketch gone (`features: 0`);
- **breadcrumb "Parts"** → same, no dialog, sketch gone;
- **page reload** → no `beforeunload`, sketch gone.

Returning to the part offers nothing: no resume band, no draft, no undo entry.
Evidence (committed, `docs/screenshots/audit-flow-2026-09/`):
`exit9-01-unsaved-sketch.png` shows four lines and nine constraints in the
strip; `exit9-03-returned.png` is the same part after Back — **"EMPTY PART —
Start with a Sketch"**. Same pair for the breadcrumb
(`exit10-01-unsaved.png` → `exit10-03-returned.png`) and for reload
(`exit11-after-reload.png`).

Back is not an exotic gesture on this class of app — a two-finger swipe on a
Mac trackpad is Back, and a modeller's hands are on the trackpad constantly.
Ten minutes of sketching is one stray swipe from gone. Note the contrast with
how carefully the *in-app* exits were built: Escape is correct in four distinct
contexts and a viewport click is explicitly non-destructive. The navigation
exits were simply never part of that design.

**System-level fix (one seam, three exits):** a `hasUnsavedSketch` guard in
`apps/web/src/routes/**` that (a) registers a TanStack Router `beforeLoad`
block with an in-app *"Finish or discard this sketch?"* dialog offering the
strip's own two verbs, and (b) registers `beforeunload` for the browser exits.
Better still, and cheaper to live with: **autosave the sketch draft** keyed on
part id, and show a resume band on return — then the guard is a courtesy rather
than the only thing between the user and data loss.
**Assertion:** draw four entities, call `page.goBack()`, expect either a
blocking dialog or, on return, a resume affordance naming the unsaved sketch.

*(The 60/120 ms boundary in F-1 was re-measured in a quiet window — load
average 0.34 rising to 1.85 — and is byte-identical to the measurement taken at
load 4.30. It is a React commit boundary, not contention.)*

### 🟠 P1 · F-3 — a solved sketch proposes nothing at all
**Fails:** *the next step is visible from the current state* — the mandate's
first flow test, quoted almost verbatim: *"A solved sketch's likely next action
is extrude — present, with the profile pre-selected, not hunted for in a
toolbar."* **NEW as a measurement; it is the flow half of the same sentence
whose selection half is already done.**

The instant after `eval-status` reads `Solved`:

```
{"editorOpen": false, "proposal": null, "resumeBand": null,
 "focused": {"tag":"BODY"}}
```

No editor, no chip, no highlight on `new-extrude`, and focus is on `<body>`.
Resting the pointer on the solved profile for 2 s proposes nothing
(`sketch-proposal` is null — the layer exists but only ever proposes
*sketch-on-face*). Pressing **E** does nothing (F-4).

So the user's eyes and hand must travel to the toolbar. **That single
transition is 8 of the 15 hunts across all three parts** — it is not one
finding, it is the shape of every feature we author.

The machinery to fix it is already in the product and proven twice:
`SketchProposal.tsx` writes a dwell-triggered, Enter-acceptable chip in the
viewport, and the toolbar already re-labels itself from history
(*"Repeat Extrude1"*). Nothing new has to be invented.

### 🟠 P1 · F-4 — the five most-used commands are the five with no keyboard shortcut
**Fails:** *the next step is visible from the current state* · keyboard-first
mandate. **NEW.**

`apps/web/src/shortcuts/registry.ts:117-124` — `PART_CREATE_SHORTCUTS` is
exactly: `P` Pattern · `S` Sweep · `L` Loft · `H` Shell · `D` Draft · `O` Hole ·
`I` Mirror. **Sketch, Extrude, Revolve, Fillet and Chamfer have none.** Verified
live: `E` on a solved sketch opens nothing.

The list is an inversion of usage. Every Fusion user's first reflex after a
sketch is `E`; ours is a dead key. The toolbar even renders this back to you —
`SweepSweepS`, `HoleHoleO`, but plain `ExtrudeExtrude`.

### 🟠 P1 · F-5 — the hole face-pick throws away the position you clicked, then asks for it again
**Fails:** *direct manipulation beats forms* · *capture intent where it forms*.
**NEW.**

Measured with two clicks at the *same pixel* (`zzflow-part1b.spec.ts`):

Screens: `p1b-01-hole-after-face-click.png` (the editor immediately after the
off-centre click) and `p1b-02-hole-after-point-click.png` (after the second,
redundant pick).

| Gesture | `hole-position` | X | Y |
| --- | --- | ---: | ---: |
| Click the face at the target spot | `Centre of face (50, 25, 20 mm)` | 50 | 25 |
| Arm "Point ▸ Change", click the **identical pixel** | `35.6, 28, 20 mm` | 35.64051 | 28.00678 |

The app can resolve that click to a point on the face — it does so the second
time. The first time it keeps the face and discards the position, then leaves
the user in an editor whose Point row says *"Centre of face"*, which reads like
a setting rather than a default that ignored them.

Cost per hole: **+1 mode switch, +2 clicks, +2 hunts**. Fusion's Hole (recalled)
places the hole where the click lands; the centre is what you get by snapping
to it, not by default.

### 🟠 P1 · F-6 — consecutive identical features share nothing
**Fails:** *the next step is visible from the current state*. **NEW.**

Second hole, opened immediately after the first was created:
`{"diameter":"6","face":"Click a face"}` — the diameter reverts to the app
default, not the 8 mm just used; the face is empty again. Re-doing hole 2 cost
**5 clicks and 6 keystrokes** to re-state a decision made 15 seconds earlier.
There is no *repeat-last-feature* affordance
(`{"repeatBtn": false, "lastCommandHint": null}`). The toolbar's
*"Repeat Extrude1"* is `new-pattern` — a pattern feature, a different thing.

Two holes is the median case, not an edge case: a plate with one hole is rare.

### 🟡 P2 · F-7 — an open command locks all 18 tools, so every feature is a full round trip
**Fails:** *the next step is visible from the current state*.
**NEW as a measurement.**

While any editor is open, every tool in the band reads *"Finish Extrude first"*
/ *"Finish Hole first"* — including `new-sketch`. The modality itself is
defensible (Fusion is modal too, and the reasons are legible, which is a
credit). The cost is structural: because the current command cannot hand off to
the next one, **every feature begins at the toolbar**, which is what makes F-3's
hunt repeat rather than happen once.

### 🟡 P2 · F-8 — Fillet opens on "All edges" with Create one keystroke away
**Fails:** *the tool proposes, the user disposes* — this proposes the
destructive option. **NEW.**

`fillet-edges` defaults to `all_edges` ("By rule"), `fillet-radius` is
autofocused at 2, and the footer reads `Create · Enter`. On the two-hole plate
that means a stray Enter rounds all twelve box edges *and* both hole rims. The
`Pick edges` mode exists (`fillet-mode-pick`) and is the right default for a
part that already has a body — "by rule" is the power move, not the opening
move.

### 🟡 P2 · F-9 — nothing on the model says "this dimension is editable"
**Fails:** *direct manipulation beats forms*. **NEW.**

Re-editing the revolve profile worked (double-click the `40` glyph → editor),
but the glyph carries no hover affordance to say so; I only tried the
double-click because it is the CAD idiom. One measured hunt, every parametric
edit.

### 🟡 P2 · F-10 — precision fields were each reached by pointer
**Fails:** keyboard-first. **NEW — and PARTLY UNVERIFIED, flagged as such.**

Typing a hole's X, Y and diameter cost **2 clicks + 6 keystrokes** in my run
because I reached each numeric cell with the pointer. **I did not measure
whether Tab walks the Hole editor's fields in fill order** — that is the
question FLOW-C3 should answer first, and if Tab already works the item
shrinks to a discoverability fix rather than a behaviour one. What IS measured
is that the draw-time cells teach `Tab switches` inside the sketch, so the
idiom is established and a user will try it; whether it holds in the feature
editors is open.

### ⚪ P3 · F-11 — the viewport nav cue never goes away on its own
`nextCue` read *"Move the view · Drag orbit · Scroll zoom · Right-drag pan ·
Got it"* on **every** state snapshot across all three parts, including after
four features had been authored. It is dismissible; it is not self-dismissing,
and a user who has already orbited has demonstrably read it.

---

## Open items from the 2026-07-24 pass — status this pass

| 2026-07-24 finding | Status now | Evidence |
| --- | --- | --- |
| P1 — Escape ignored when focus is outside an editor | ✅ **CLOSED** | EXIT 5/6: editor closes either way, feature not created |
| P1 — exact dimensions are the give-up point (no select→D hint) | ✅ **superseded** by FB-16 draw-time cells — you never need select→D for a shape you are drawing | Part 1 step 6 |
| P1 — extrude on an open profile fails with *revolve* instructions | ⬜ **not re-tested** (out of this pass's three parts) | — |
| P2 — "Solve a sketch first" gates in solver jargon | ➖ **partly** — gate copy is now per-tool and plainer (*"Draw a sketch to extrude"*) | empty-part tool snapshot |
| P2 — disabled-tool tooltip clipped by the tree panel | ⬜ sibling auditor's ground, not re-reported here | — |
| P2 — the Hole editor covers its own "click a point" target | ➖ **changed shape**: the point is no longer the primary gesture (F-5 is now the defect) | Part 1b |
| P2 — features can't be deleted | ✅ **CLOSED** — `requestDeleteFeature` + `FeatureDeleteConfirm` with a dependents list | `PartPage.tsx:4495,4547` |
| P2 — feature errors land where the novice isn't looking | ✅ **CLOSED** — a `role="alert"` rebuild notice with a Dismiss, plus the ERR row | `rebuild-failure.png` |
| P2 — undo/redo are 32 × 16 px targets | ⬜ sibling auditor's ground | — |

**Three of the nine are closed and one is superseded. The loop IS closing
findings** — which is why the two P0s above matter: they are both in code that
shipped *after* that pass.

---

## Proposed roadmap

Ordered so each wave ships alone and the earliest wave buys the most
seamlessness per unit of effort. Across the three ledgers 15 hunts were
recorded; waves 1–3 address 13 of them and close both P0s.

Every item names: the ONE subtree it lives in · the surface · **what proposes
it at the right moment** · the e2e assertion that proves a user can do it.
"The user opens a menu and finds it" is not a proposal mechanism and does not
appear below.

### Wave 1 — stop losing work, stop advertising readiness we don't have
*Closes both P0s. Smallest diff in the whole plan; nothing else is worth
shipping until a sketch cannot evaporate.*

**FLOW-A1 · The first keystroke after a draw always lands**
- Subtree: `apps/web/src/viewport/**` (`SketchScene.tsx`, the draw-dimension
  block)
- Surface: the size cells at the cursor, immediately after a rectangle /
  circle / line is placed.
- Proposes it: the cells already do — they render `armed` and say *"Type a
  size"*. The fix is to make that promise true from the first frame: focus the
  width cell in the same commit that places the shape (so the browser delivers
  the character), or buffer keys from `armed` and replay on attach.
- Assertion: place a rectangle, then `page.keyboard.press("1")` with **no
  intervening round trip**; `draw-dimension-width` must read `1`. Parameterise
  the existing race sweep at 0/30/60/120 ms — all four must pass.

**FLOW-A2 · An unsaved sketch cannot leave the building quietly**
- Subtree: `apps/web/src/routes/**` (a `useUnsavedSketchGuard` beside
  `PartPage`)
- Surface: browser Back, breadcrumb navigation, tab close / reload.
- Proposes it: the *attempt to leave* proposes it. An in-app dialog carrying
  the sketch strip's own two verbs (FINISH / DISCARD) for router navigations;
  `beforeunload` for the browser ones. Ship a per-part **draft autosave** in
  the same item so the dialog is a courtesy, not a dam.
- Assertion: draw four entities; `page.goBack()`; expect either a blocking
  dialog **or**, on returning to the part, a resume affordance naming the
  unsaved sketch. Repeat for the breadcrumb link and for `page.reload()` —
  three exits, one assertion body.

### Wave 2 — the next step proposes itself
*Removes 8 of the 15 measured hunts. This is the wave the founder's first flow
test is actually asking for, and it is cheap because the proposal machinery
(`SketchProposal.tsx`) and the contextual re-labelling (*"Repeat Extrude1"*)
both already exist.*

**FLOW-B1 · The solved sketch offers its extrude, in the viewport, where the
sketch is**
- Subtree: `apps/web/src/viewport/**` (a second consumer of
  `sketch-proposal-layer`, not a new layer)
- Surface: a dwell-free chip anchored to the just-solved profile — *"Extrude
  Sketch1 · ⏎"* — appearing the moment `eval-status` turns `Solved`, and
  withdrawing on any other action.
- Proposes it: **the solve completing.** Not a hover, not a menu — the state
  transition itself. Accepting it opens the Extrude editor with the profile
  already set (which it already does) and the distance autofocused (which it
  already does), so the whole item is the chip and the Enter binding.
- Assertion: finish a sketch; without moving the mouse, assert a visible
  element whose accessible name contains "Extrude"; press Enter; assert
  `extrude-editor` is visible and `extrude-profile` names that sketch.
  Negative control: the chip must be gone after the user clicks anything else.

**FLOW-B2 · Give the five most-used verbs their keys**
- Subtree: `apps/web/src/shortcuts/**` (`registry.ts`)
- Surface: the whole workspace; the toolbar tooltips render the letter for
  free, so the palette teaches itself the moment the registry knows.
- Proposes it: the toolbar — every other verb already prints its letter, so
  the five blanks currently read as *"this one has no shortcut"*, which is
  exactly right and exactly wrong.
- Keys: `E` Extrude · `R` Revolve · `F` Fillet · `C` Chamfer · `K` Sketch
  (`S` is taken by Sweep; do not steal it — a moved shortcut is worse than a
  missing one).
- Assertion: with a solved sketch and nothing focused, `press("e")` opens
  `extrude-editor`. Plus a registry test that no two commands claim one key.

**FLOW-B3 · After a feature builds, say what usually comes next**
- Subtree: `apps/web/src/components/**` (extend the tool band's existing
  contextual labelling, not a new panel)
- Surface: the tool band, immediately after `eval-status` returns to `Solved`.
- Proposes it: the successful build. One quiet accent on the single most
  likely next verb, chosen from the feature just created (extrude → hole or
  fillet; hole → repeat-hole; revolve → fillet). Not a wizard; one highlighted
  key among the existing buttons.
- Assertion: create an extrude; assert exactly one tool carries
  `data-next-step="true"` and that it is enabled.

### Wave 3 — a pick carries the intent it was made with
*Removes 4 more hunts and 4 clicks per hole. This is `direct manipulation beats
forms` applied to the one place a form still wins.*

**FLOW-C1 · The face click seeds the hole where you clicked**
- Subtree: `apps/web/src/routes/**` (`PartPage.tsx` — `holePick` /
  `setHolePointPicked` already receive the point; the face path just drops it)
- Surface: Hole editor, first click on the body.
- Proposes it: **the click itself.** The Point row fills from the same hit,
  and the X/Y cells show the resolved coordinates, so the user's next act is
  *correcting* a number rather than *supplying* one. Snap to the face centre
  and to bore centres inside a small radius, so "centre of face" stays one
  easy gesture.
- Assertion: open Hole, click the top face at a point measurably off-centre,
  assert `hole-position-x` is **not** the face-centre X and matches the
  clicked point within tolerance. (The current behaviour makes this assertion
  fail today — that is the point.)

**FLOW-C2 · The next feature of the same kind starts from the last one**
- Subtree: `apps/web/src/store/**` (a `lastFeatureDefaults` slice; the editors
  read it as their initial form state)
- Surface: every feature editor's opening values.
- Proposes it: opening the same command again within the session. Hole after
  a hole opens at 8 mm through-all, not 6 mm blind. A visible *"same as
  Hole1"* line in the editor, one click to reset to defaults, so nothing is
  hidden.
- Assertion: create a hole at Ø8 through-all; open Hole again; assert
  `hole-diameter` reads `8` and the depth mode is through-all.

**FLOW-C3 · Tab walks a feature editor in fill order**
- Subtree: `packages/design/**` (the editor card / `NumberField` primitive —
  fix the primitive, not seventeen editors)
- Surface: every feature editor.
- Proposes it: the caret. The draw-time cells already teach *"Tab switches"*;
  this makes that promise hold past the sketch boundary.
- Assertion: open Hole with a face picked; from `hole-position-x`, three Tabs
  reach `hole-diameter`; no pointer events in the whole test.

### Wave 4 — remove the remaining sharp edges
*Not flow-critical; cheap and each one is a paper cut every part.*

**FLOW-D1 · Fillet opens on "Pick edges" when a body exists**
- Subtree: `apps/web/src/components/**` (`FilletEditor` / `ChamferEditor`)
- Surface: the Selection segmented control.
- Proposes it: the presence of a body. "By rule / All edges" stays, one click
  away, for the case where it is genuinely what you want.
- Assertion: with a body present, opening Fillet leaves `fillet-submit`
  gated until at least one edge is picked, and the gate states its reason.

**FLOW-D2 · A dimension glyph looks editable**
- Subtree: `apps/web/src/viewport/**` (the glyph renderer)
- Surface: every dimension in an open sketch.
- Proposes it: hover. Cursor + a token-coloured underline; double-click keeps
  working, and single-click-then-Enter joins it for the keyboard.
- Assertion: hover a `glyph-*` carrying a number; assert the hover state is
  distinguishable (computed style differs) and that Enter on the focused glyph
  opens `dimension-input`.

**FLOW-D3 · The nav cue retires itself**
- Subtree: `apps/web/src/components/**` (`NavCue`)
- Surface: the viewport corner.
- Proposes it: nothing — it should *stop* proposing. Dismiss automatically
  after the user has orbited and zoomed once, and persist that per account.
- Assertion: orbit and zoom the viewport; assert `nav-cue` is gone and stays
  gone after a reload.

### Explicitly NOT proposed
- **The extrude drag handle.** `extrude-depth-handle` /
  `extrude-depth-readout` / `extrude-depth-steps` are already mounted. Judging
  the feel of it belongs to the sibling audit; rebuilding it would be waste.
- **The revolve editor.** One keystroke from a solved profile to a correct
  revolve, with inferred axes in the dropdown. Leave it alone — and copy it.
- **The rebuild-failure surface.** Named cause, named parameter, the last good
  body still on screen, dismissible alert, undo available. This is the
  standard the rest of the app should be measured against.
- **Feature delete and its dependents confirm.** Shipped; closed.
- **Draw-time dimension cells as a concept.** Correct and Fusion-grade; only
  the first-keystroke race (FLOW-A1) is wrong with them.

---

## Evidence

Instrumented specs written for this pass. They were **removed from
`apps/web/e2e/` after the run** so they cannot turn anyone's lint red or join
a shard; copies are in the session scratchpad
(`flowaudit/specs/`) for whoever picks up Wave 1, and the assertions worth
keeping are restated as the per-item acceptance tests in the roadmap:
`zzflow-ledger.ts` (the four-number ledger), `zzflow-part1.spec.ts`,
`zzflow-part1b.spec.ts`, `zzflow-part2.spec.ts`, `zzflow-part3.spec.ts`,
`zzflow-exit.spec.ts`, `zzflow-exit2.spec.ts`, `zzflow-race.spec.ts`,
`zzflow-final.spec.ts`.

Eleven key frames are committed to
**`docs/screenshots/audit-flow-2026-09/`**; the full capture set and the raw
per-step JSON stayed in the session scratchpad. The two frames to look at first
are `exit9-01-unsaved-sketch.png` → `exit9-03-returned.png` (four entities and
nine constraints, then "EMPTY PART"), and `rebuild-failure.png` for contrast —
the surface that gets error handling exactly right.

