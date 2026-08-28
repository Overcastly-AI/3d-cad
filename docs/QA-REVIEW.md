# QA review — end-to-end, on the real artifact

Independent QA of the shipped product: the real stack, a real browser, real
modelling flows, desktop **and** touch. Geometric correctness is
`docs/GEOMETRY-QA.md`'s beat; this file records what a working engineer would
hit while USING the thing, including geometry that reaches a user through a
shipped flow (a wrong solid on screen is a QA defect no matter whose code made
it).

Severity: **P0** silently wrong artifact or data loss · **P1** a daily flow is
blocked or lies · **P2** a real flow is worse than it should be · **P3** polish.

---

## 2026-08-28 — the `force: true` audit: all 22 call sites, measured

**Verdict: 18 of 22 were pure cargo, 1 was hiding an assertion that could never
fail, 3 were legitimate but unproven. Nothing in the suite still hides an
unhittable target — but the audit found one NEW product defect the specs could
never have caught, because no spec picks an edge that small.**

**The count the audit was for.** Yesterday's `dimension-placement` finding was a
zero-area SVG `<line>` hit region, fixed with a rotated `<rect>`. The question
was whether that was one bad affordance or a systemic pattern. **It was one.**
Re-measured on the branch tip, every drawing pick target now has real area and
answers `elementFromPoint` at its own centre: the hole circle **39.0 x 39.0 px,
18/18 sample points**, the 40 mm edge **156.2 x 10.2 px, 14/18, centre resolves
to itself**, the vertex handles **20.3 x 20.3 px, 18/18**. Removing `force` from
all 18 drawing picks and re-running: **48/48 green**, no product change, no
assertion weakened. The flag was residue of the defect that is already fixed.

(NB the file count was 25 in the brief; three of those are prose in
`dimension-placement.spec.ts` describing the fix. There were 22 real calls.)

| call site | class | measured |
| --- | --- | --- |
| `drawings.spec.ts` x9 | **(a) cargo** | circle 18/18, lines 14/18, vertices 18/18 — all reach centre |
| `drawing-wall-thickness.spec.ts` x4 | **(a) cargo** | shell wall faces, plain `.click()` green |
| `qa-wave-0730.spec.ts` x4 (drawing picks) | **(a) cargo** | same targets |
| `drawing-reanchor.spec.ts` x1 | **(a) cargo** | 100 mm top-view edge |
| `body-status.spec.ts` x1 | **(d) legitimate** | `aria-disabled` export cell, centre resolves to itself |
| `pick-no-body.spec.ts` x1 | **(d) legitimate** | `hole-face-pick`, centre resolves to itself |
| `qa-wave-0730.spec.ts:857` x1 | **(d) legitimate** | `part-export-step`, centre resolves to itself |
| `nav-chrome.spec.ts:199` x1 | **VACUOUS** | see below |

### P2 (test integrity, now fixed) — the forced click never reached the button

`nav-chrome.spec.ts:199` claimed "a stray click on the locked Extrude is inert —
the Fillet command and its picked edge survive". While a command is open,
`CreateStrip` gives the whole `tool-groups` band `sr-only`: measured
**`1x1@(-1,43)`, `clip: rect(0,0,0,0)`, `overflow:hidden`** — the button is
clipped out of the frame. `checkVisibility()` and Playwright's `isVisible()`
BOTH return true for `sr-only`, which is why nobody noticed. `force` skips the
hit-target check, so the synthetic click went to whatever was topmost at those
coordinates: **measured, it landed on `header[topbar]`**, and the Extrude
handler was never invoked. The three assertions that followed would have passed
identically had the handler discarded the picks — the one thing the test exists
to catch. Same family as `toBeVisible()` on an off-frame SAVE control.

The product behaviour is genuinely correct: dispatching the activation directly
at the button (`el.click()`) leaves `fillet-editor` open, the selection at
`"1 edge picked"`, and `extrude-distance` at count 0. So the fix is the spec's.
It now asserts the two halves separately — that the band is clipped (no pointer
can reach it) and that a direct activation is refused by the handler.

### P2 (product, NOT fixed — needs a `DrawingSheet` change) — a small feature's edge cannot be picked at all

The already-filed finding is that the always-present vertex hit rects take 4 of
18 points on a 40 mm edge. **The severity is worse than "an invisible control
beats a visible one": below a threshold the edge disappears entirely.**

A `VertexHandle`'s transparent target is `pickHitMm` (2.6 mm) in every
direction, so the two endpoint rects together consume **5.2 sheet-mm** of any
straight edge, from both ends, regardless of how long the edge is. Measured on a
laid-out 40 x 25 x 10 plate: a 156.2 px (40 mm) edge loses 6/41 sample points,
a 97.6 px edge loses 10/41, and a 39.0 px (10 mm) edge loses **22 of 41 — more
than half the edge is not the edge**.

Below 5.2 mm there is nothing left. Confirmed by construction rather than
arithmetic, on a 40 x 4 x 10 rib:

```
top/line len= 15.6px  reachable= 0/41   centre -> drawing-pick-vertex
top/line len=156.2px  reachable=35/41   centre -> drawing-pick-edge
top/line len=156.2px  reachable=35/41   centre -> drawing-pick-edge
top/line len= 15.6px  reachable= 0/41   centre -> drawing-pick-vertex

real page.mouse.click at the SHORT edge's centre:
  dimension-author-menu = false      <- the user's actual intent
  dimension-pick-hint   = true       <- silently armed a point-to-point pick
```

So a user aiming at a 4 mm edge to dimension it does not get "nothing happens" —
they get a DIFFERENT TOOL, with no explanation, and the sheet is now waiting for
a second vertex they never asked to pick. The threshold scales with sheet scale:
5.2 mm of paper is a 5.2 mm feature at 1:1, 10.4 mm at 1:2, 26 mm at 1:5. Thin
ribs, wall thicknesses and small bosses on a scaled-down sheet are all inside it.

Not fixed here: the cure is in `apps/web/src/components/DrawingSheet.tsx`
(`VertexHandle`'s always-present rect), which a concurrent agent holds. Two
shapes worth considering — clamp the vertex rect to a fraction of the shorter
adjoining edge, or make the always-present vertex target conditional on the
point-to-point pick actually being armed (it is already drawn conditionally;
only the hit rect is unconditional, and the comment says it is unconditional so
a *forced* e2e click can reach it — a reason that no longer exists now that no
spec forces).

### The guard, so this cannot come back quietly

`force: true` now appears exactly once in `apps/web/e2e/`, inside
`clickRefusedControl` in `support.ts`. It asserts the control has real area AND
that a pointer aimed at its centre resolves to the control, and only then forces
the event past the `aria-disabled` actionability check. **Negative control run,
because a guard that cannot fail is not a guard**: pointed at the sr-only locked
Extrude it refuses with `a pointer aimed at the control's centre lands on
h2[feature-tree-section] instead`.

**Method / load.** Native stack per CLAUDE.md (registry 403-blocked): geometry
:8032, documents :8031, gateway :8030 on agent-prefixed SQLite files, Vite
:5230, real Chromium at 1600x1000. The final 48-test sweep ran with one sibling
agent's Playwright live, load average **1.5 on 4 cores** — noted because a red
run under load is unconfirmed; this one was 48/48 green, so the load is
irrelevant to the verdict. All measured values above were reproduced across
separate runs with identical numbers. NB `apps/web/playwright.config.ts` defines
no touch project, so the "desktop AND touch" half of the QA remit has no
harness to run in for these files.

---

## 2026-08-27 — REACH batch, independent QA (REACH-1 / REACH-2 / REACH-3)

> **Provenance note (annotation, not a rewrite).** This entry, the QA-R1/R2/R3
> board items and `apps/web/e2e/qa-reach-batch.spec.ts` were staged by the
> qa-tester and then captured by a concurrent agent's commit `4e41eb4`
> ("fix(workflow): a subtree missing from the list is invisible…"), whose
> message describes none of them. Nothing was lost and `4e41eb4` was already
> pushed, so the record is corrected here rather than by rewriting history other
> agents have rebased onto (CLAUDE.md staging protocol). The QA work is the
> qa-tester's; the workflow change in that commit is not.


**Verdict: REACH-2 and REACH-3 PASS. REACH-1 FAILS — it ships a control that
takes the sketch's own FINISH and CANCEL out of the window at the two most
common laptop widths, and an angle annotation that keeps a number the solver
has already moved off.** Everything else in the batch survived the second edit,
the reload, the delete, the tab switch and the tap.

**Method.** Native stack per CLAUDE.md (Docker registry is 403-blocked):
geometry :8072, documents :8071, gateway :8070, on agent-prefixed SQLite files
created fresh. Real Chromium at 1280x800 / 1440 / 1600 and in a `hasTouch`
context. Load average during every run **0.7-3.7, all of it mine** (my own
Playwright + three uvicorns; no other agent process above 1.1 % CPU), so no run
here is a contention artefact. Every defect below was reproduced **3x with
byte-identical measured values** — a moving failure point would have meant
flake, and none moved. New spec: `apps/web/e2e/qa-reach-batch.spec.ts`
(14 cases, 3 of them `test.fail()`-annotated to encode the open defects).
The builders' own specs were also re-run on the INTEGRATED tip (`9284e82`):
sketch-vocab + pattern-scope + sheet-convention + pattern + mirror +
constraints + drawing-sheets = **34 passed**.

### QA-R1 (P1, REACH-1) — a live selection puts FINISH SKETCH and CANCEL SKETCH outside the window

Not a layout nit: it is measured **functionally**. With two lines selected at
1280x800 the sketch strip runs to **1413 px in a 1280 px window** and
`document.documentElement.scrollWidth === clientWidth`, so there is nothing to
scroll to. A real `page.mouse.click` at `sketch-save`'s own centre does
**nothing** — the strip is still there afterwards. The user's only exit from
the sketch is the keyboard, and nothing on screen says so.

Identical every run (3x):

```
STRIP-CENSUS {"clipped":[
  {"testId":"constraint-group-relational","left":1167,"right":1300},
  {"testId":"sketch-construction","left":1302,"right":1334},
  {"testId":"sketch-save","left":1347,"right":1379},
  {"testId":"sketch-exit","left":1381,"right":1413}],
  "scrollable":false,"width":1280}
```

Width sweep, with the selection re-picked after each resize (`RAIL-BUDGET`):

| width | 0 offers | 1 offer (one line) | 3 offers (two lines) |
|---|---|---|---|
| 1280 | clean | **`sketch-exit` clipped** | **relational + construction + save + exit** |
| 1366 | clean | clean | **`sketch-save` + `sketch-exit`** |
| 1440 | clean | clean | clean |
| 1600 | clean | clean | clean |

Two things this adds to the frontend-qa spot-check (`docs/UI-REVIEW.md`
2026-08-27 P1-1), which measured the same 1280 numbers: **(a) 1366 also fails**
— the single most common laptop width in the wild, and one nobody measured;
**(b) ONE offer is enough** — selecting a single line, the most ordinary state
in a sketcher, already costs the user CANCEL SKETCH at 1280. So this is not an
edge case reachable only by an unusual multi-select.

*Why no existing assertion catches it:* Playwright's `toBeVisible()` is a
CSS/box property, not a viewport-containment one — `sketch-exit` at x=1381 on a
1280 frame is "visible". The builder's own 1280 case
(`sketch-vocab.spec.ts:599`) asserts the offer appears and takes a screenshot;
both are true while the strip overflows behind them. The census helper in
`qa-reach-batch.spec.ts` (`clippedControls`) is the shape of gate that can see
this, and is worth lifting into a shared helper for every strip.

### QA-R2 (P1, REACH-1) — the angle glyph keeps a value the solver has moved off

Reproduced end to end and measured against the EVALUATE payload, not inferred:
author `A` = 30 deg, re-open the same glyph, type `15*3`, Enter. The server
resolves it and the model moves; the annotation does not.

```
ANGLE-EXPR {"shown":"30°","solved":45}      (identical on 2/2 repeats)
```

An annotation that contradicts the geometry is worse than an absent one because
it looks authoritative, and REACH-1 is the commit that made this state
reachable — before it, no user could author an angle at all. Independently
confirms `docs/UI-REVIEW.md`'s P1-2 and adds the geometric measurement
(`solved = 45.000` from the solver, against a glyph reading `30°`). Cause is
already known and documented in the code: degrees ride `SolvedSketch.angles`,
which `apps/web/src` never reads
(`apps/web/src/sketch/constraints.ts:1333-1338`).

### QA-R3 (P2, REACH-1) — on touch, four of the five new verbs cannot be reached at all

The rail's keycaps ARE real buttons and tapping one works (verified: tap
`verb-hint-angle` -> the angle editor opens -> 30 deg applies). The problem is
upstream of the rail: **a touch device cannot hold two entities.**

```
TOUCH-ADDITIVE {"plain":"1 ent · 2 applied",
                "held":"1 ent · 2 applied",
                "offers":["verb-hint-distance"]}
```

A plain second tap REPLACES the selection; a 900 ms long press (dispatched as a
real touch sequence over CDP) does the same. Additive selection is Shift-click
only. So on a keyboardless tablet the rail can only ever offer single-entity
verbs, and **angle, collinear, symmetric_lines and midpoint — four of REACH-1's
five — are unreachable**. `scripts/check-ui-parity.py`'s 84/120 is a
desktop-only number and should say so.

### What passed, and what was specifically probed to make it mean something

- **REACH-2, the second edit.** Author a 6-up `features`-scoped pattern, re-open
  it from the tree, change ONLY the count to 4, submit: the scope holds. Proved
  on GEOMETRY, never a 2xx (params models are `extra="ignore"`) — with the 3 mm
  fillet in the chain that separates the two readings, the 4-up removes exactly
  `3 x pi x 4^2 x t` more than the filleted plate. Reload agrees; the tree badge
  still reads `pattern · Hole1`.
- **REACH-2, deleting the subject.** Right-click Hole1 -> Delete while Pattern1
  scopes it: `data-blocked=true`, the dependent is NAMED (`Pattern1`), no delete
  offered, and cancelling leaves the volume untouched. The scope ref is a real
  dependency edge, not just a param.
- **REACH-2, a pattern OF a pattern.** The UI offers it (a features-scoped
  pattern is a legal subject), and the kernel honours it: solves, and removes
  strictly more material. The offer is not a trap.
- **REACH-3, per-sheet state.** Sheet 1 first-angle + sheet 2 third-angle,
  switch between tabs, reload: each sheet keeps its own convention. A new sheet
  INHERITS the convention of the sheet it was made from, then diverges freely.
- **REACH-3, the deliverable.** The exported PDF follows the paper:
  `PDF-BOXES {"landscapePdf":{"width":841.89,"height":595.28},
  "portraitPdf":{"width":595.28,"height":841.89}}`. A portrait sheet does not
  export landscape paper.
- **REACH-3, the header strip at 1280.** Two new cells, zero clipped controls.
- **Cross-item, the command band at 1280.** REACH-2's renamed verb
  ("Repeat Hole1 — place it in a linear or circular array (P)") costs no command
  its place: `BAND-CENSUS-PROPOSING {"clipped":[],"scrollable":false}`. The band
  measures itself into the icon tier instead, which is the UI-REVIEW finding
  about discoverability — not an overflow.
- **Cross-item, key shadowing.** `I` is collinear in the sketch and Mirror in
  the model; likewise P/H/D/O/S/L. Pressed all seven with a live sketch
  selection and a body present (so every model opener was ENABLED): no editor
  opened, the sketch stayed up. The `mode !== "off"` gate holds.
- **REACH-1, across a save.** An angle authored with `A` survives finish ->
  re-open (tree Edit): the glyph comes back reading `30°`, the editor prefills
  the PERSISTED 30 rather than re-measuring, and re-driving it to 45 moves the
  model and the glyph together. QA-R2 is specific to the expression/reference
  path, not to persistence.
- **Touch, the other two items.** `pattern-scope-body` / `pattern-scope-features`
  and both REACH-3 header cells answer a tap, and the hole editor's own Cancel
  dismisses without an Escape key.

### Observations (not defects)

- REACH-2's proposal does not survive a trip through the sketcher: enter and
  leave a sketch and the Modify verb reverts to plain "Pattern". That is
  CONSISTENT — the tree selection is dropped at the same moment
  (`feature-select-2 aria-pressed=false`), so the verb and the tree never
  disagree about the subject. Noted because "the selection survives Escape" is
  load-bearing for this feature and "it survives a sketch" is not.
- `test.fail()` with no argument at DESCRIBE level marks every sibling test in
  that suite, not the next one. It cost a false red here (a passing
  key-shadowing case reported as "Expected to fail, but passed"). Scope it
  inside the test body.

## 2026-08-01 — founder session: the picking reports, measured (FB-2/3/5/6/9)

The founder modelled for an evening and reported, among others, that a sketch
line "wouldn't even select", that picking a face was "very difficult", that a
sketch could not be attached to a face at all, that sketch ink could not be
seen, and — from a photograph of an open `EDIT EXTRUDE` — that "the extruded is
not on the same plane". This pass reproduced each in a real browser and
replaced every impression with a number.

**Method.** Detached `git worktree` at HEAD (the tree had four agents' live
uncommitted work, so the branch tip could not be trusted to be the artifact).
Native container-free stack on isolated ports — geometry :8022, documents
:8021, gateway :8020, Vite :5183 with `GATEWAY_ORIGIN` pointed at it — fresh
SQLite via `metadata.create_all`. Probes drove real mouse events at real screen
coordinates; the sketch store was read through the live Vite module URL so a
pick could be observed as `entity` vs `point` vs nothing, rather than inferred
from ink. Kernel numbers came from the geometry service directly, not the
screen. Commits driven: `3f4fbe6`, `d8a4126`, `3cf6650`, and `ae3980e`.

### Headline: `d8a4126` (PERF-4b) is EXONERATED — do not revert it

The suspicion was that fusing the per-face glTF primitives and re-grouping the
draw calls had broken the raycast that face picking resolves against. It had
not, and it could not have: **face picking does not use a raycast at all.**
`FacePickOverlay.tsx` places a drei `Html` DOM button (`PickNode`, 24 × 24 px)
at each planar face's centroid and `ModelMesh.tsx` carries no `onClick` or
`onPointerDown` — at HEAD, at `d8a4126`, and at `3cf6650` alike. `d8a4126`
touched neither `FacePickOverlay.tsx` nor anything under `apps/web/src/sketch/`.

Driven empirically at all three commits, the pick behaviour is **identical to
the character**:

| probe | `3cf6650` | `d8a4126` | `3f4fbe6` |
|---|---|---|---|
| hover band across a sketch line (px, dy from y=640) | −4 … +11 | −4 … +11 | −4 … +11 |
| hover along the edge (x 660…970) | entity everywhere | entity everywhere | entity everywhere |
| clean click on a line | selects the LINE | selects the LINE | selects the LINE |
| face pick markers | 6 × 24 px | 6 × 24 px | 6 × 24 px |
| body area that is a live face target | 2.2 % | 2.2 % | 2.2 % |
| click on the face SURFACE | nothing | nothing | nothing |

### FB-2 "the line wouldn't even select" — the pick math is FINE; four things around it are not

A clean click on a sketch line selects the line entity and `D` opens the
dimension editor. That is true at every commit tested and is now guarded by
`e2e/founder-picking.spec.ts`. What the founder hit is one or more of these:

1. **A click with ≥ 5 px of pointer travel is silently discarded.**
   `SketchScene.tsx:353` returns early when r3f's `e.delta > CLICK_SLOP_PX`
   (= 4). Measured threshold, exactly: `0px SELECTS · 1 SELECTS · 2 SELECTS ·
   3 SELECTS · 4 SELECTS · 5 DEAD · 6 DEAD · 8 DEAD · 10 DEAD`. Playwright's
   `mouse.click` moves zero pixels, so **no existing spec can see this** — the
   suite proves the path a human never takes. A hand on a trackpad routinely
   drifts 5–10 px, and the app's response is nothing at all: no hint, no
   cursor change, no log. This is the single best explanation of "wouldn't even
   select" and it is one constant plus a "was it a drag?" rule that should be
   about intent (did the camera actually orbit) rather than a 4 px ceiling.
   Filed **FB-12**.
2. **Escape with nothing selected ENDS the sketch.** `escapeAction`
   (`sketch/tools.ts:402`) falls through to `"exit"` for tool `select` with an
   empty selection, and `PartPage.tsx:1029` routes that to `finishSketch()` —
   which persists and closes. So the reflex after a click that appears to do
   nothing ("tap Esc, start over") throws you out of the sketcher. The strip's
   own caption advertises Esc as SAVE, so the same key in the same state has two
   advertised meanings. Filed **FB-13**.
3. **The pick tolerance is 8 px and the band is therefore 16 px wide** — fine
   for a line you can see, thin for one you cannot. Points do NOT shadow the
   segment: scanning the edge at 5 px intervals, `point` picks win only at the
   two corners (x = 650 and x = 980); everywhere between, the entity wins. That
   hypothesis is REFUTED.
4. **Every click accumulates.** `toggleSelection` (`pick.ts:168`) appends
   rather than replaces, so clicking line A then line B leaves *both* selected
   and `distance` answers "Select one line to dimension." Standard CAD replaces
   on a plain click and adds on Ctrl/Shift. A user hunting for a working click
   builds a multi-pick selection that then refuses to dimension.

### FB-3 / FB-5 face picking — 2.2 % of the body is clickable

Armed with "Pick a face", the prompt reads *"Click a highlighted planar face to
sketch on it."* Nothing is highlighted until hover, and the face itself is not
a target. The only live targets are six 24 × 24 px DOM markers at the face
centroids. Sampling the body's on-screen region on a 10 px lattice: **32 of
1457 points (2.2 %) land on a pick target**; the other 97.8 % of the solid is
dead. Clicking the top face 200 px from any marker leaves `sketch-step` at
"Pick a plane" indefinitely. On a 10 mm box the six markers crowd into a
~200 × 55 px cluster, and because drei `Html` does not occlude, the markers for
the three HIDDEN faces are drawn on top of the visible ones — so the sparse
targets that do exist are also ambiguous. "Very difficult" is generous. Evidence:
`docs/screenshots/qa-0801-face-pick-targets.png` — six white squares are the
only live targets in that frame.

The founder's expectation (hover a face → it offers a sketch) is the fix
shape; the current affordance is also a differently-named action
(`ctx-sketch-on-face`) in a right-click Tools menu, which is why the capability
reads as absent.

### FB-6 sketch ink on a face — the z-fighting diagnosis is REFUTED

The hypothesis was that `depthWrite={false}` with depth testing left on makes a
coplanar sketch z-fight into the face. It does not: the ink renders cleanly.
The actual defect is different and worse. Entering a sketch on a face puts the
camera 170 mm from a 180 mm plane card, so **the card fills the entire frame as
a single featureless light-grey slab** — no grid, no body silhouette, no edges,
no scale, no relation to the part you are sketching on. Compare the base-plane
control, which shows the adaptive grid on a dark field. The ink is then white
on light grey rather than the scribe blue on dark, which is a contrast problem
on top of a context problem. Fixing depth state alone would change nothing.
Evidence: `docs/screenshots/qa-0801-sketch-on-base-plane.png` vs
`docs/screenshots/qa-0801-sketch-on-face-grey-slab.png`.

`countSketchInkPixels` in `e2e/support.ts` cannot gate this: it counts *bright,
cool-tinted* pixels, and on a face it returned 926 729 (the lit face itself) vs
1 881 on a base plane — so the helper's number goes UP by three orders of
magnitude when the sketch becomes unusable. A gate built on it would have
passed. No spec exercises sketch-on-a-face ink; that is a real gate-shaped hole.

### FB-9 "the extruded is not on the same plane" — the KERNEL IS EXACT

Driven against the geometry service directly (a 40 × 25 rectangle, extrude
10 mm, ADD, direction NORMAL). Every number is exact to the digit printed:

| sketch plane | volume (mm³) | bbox min | bbox max | centroid |
|---|---|---|---|---|
| XY (z = 0) | 10000.000000 | 0, 0, **0.0** | 40, 25, **10.0** | 20, 12.5, 5 |
| XZ (y = 0) | 10000.000000 | 0, **−10.0**, 0 | 40, **0.0**, 25 | 20, −5, 12.5 |
| YZ (x = 0) | 10000.000000 | **0.0**, 0, 0 | **10.0**, 40, 25 | 5, 20, 12.5 |
| XY + 30 datum | 10000.000000 | 0, 0, **30.0** | 40, 25, **40.0** | 20, 12.5, 35 |

The base face lies exactly ON the sketch plane in all four cases (solid min
along the normal = the plane's own offset, to 0), the footprint is exactly the
profile (no lateral offset, centroid at the profile centre), and the offset
datum tracks its 30 mm with no drift between the ink placement and the kernel's
plane origin. XZ builds along −Y and YZ along +X, which is the right-hand
convention (XZ's normal is X × Z = −Y) — consistent, not a sign bug. The same
numbers reach the UI unchanged: the browser's inspector read `48 × 10 × 32`,
min `−22, −10, −17`, max `26, 0, 15` for the equivalent XZ case.

**So FB-9 is not wrong geometry.** The remaining candidates are (a) the camera
snap the founder was still living with when the photo was taken — `5bd4c46`
landed mid-session and fixes it — and (b) a stale bundle: the founder tests
from a GitHub Codespace (`app.github.dev`), two fixes landed during the
session, and nothing in the app says which build is running (**FB-11**). A
stale client and a live regression are indistinguishable from a photograph.
Recommend settling FB-9 by asking the founder to reproduce on a named build.

### Verdict

**FB-2 does NOT reproduce as stated** — a clean click selects the line at HEAD
and at both bisect points. **FB-12 (drag slop) and FB-13 (Escape exits) are
the reproducible defects behind the report**, and both are invisible to the
existing suite by construction. **FB-3/FB-5 reproduce exactly** and are
quantified above. **FB-6 reproduces but with a different cause than diagnosed.**
**FB-9 does not reproduce at the kernel; the geometry is exact.**

Regression spec: `apps/web/e2e/founder-picking.spec.ts` — one passing baseline
guard plus three `test.fail()` tests that encode FB-12, FB-13 and FB-3/FB-5 as
they behave today. They keep the suite green while the bugs are open and turn
it red the moment a fix lands without the annotation being removed; deleting
the annotation is part of each fix.

---

## 2026-08-01 — dogfooding pass #3: the imported-STEP remix (interop)

The recurring **Model-a-REAL-part gate**, third pass (WB-64 and TB-1 were
#1/#2). Scenario: *a vendor ships you a STEP, you remix it into your own
bracket, then the vendor ships rev B.* Chosen because the day's two perf
commits both live on that path — `d8a4126` (PERF-4b, glTF per-face primitives
FUSED below 12 tris/face with the partition in a side table) and `dd8b2ba`
(PERF-5b, face provenance fingerprinted at production time instead of retaining
snapshot B-reps). An imported body is dense, so it exercises the UNFUSED side;
a milled plate is sparse and exercises the FUSED side. Both were driven.

**The part.** A NEMA 17 stepper front end-plate — the thing you actually
download from a motor supplier and build a mount around. 42.3 mm square with
4× 5 mm corner chamfers, 8 mm thick, Ø22×2 pilot boss, Ø5.2 shaft bore, 4× Ø3
on a 31 mm square. Authored OUTSIDE the app with build123d and committed as
`apps/web/e2e/fixtures/nema17-front-plate.step`, so the app sees an opaque
B-rep with no feature tree behind it. Closed form: 13 914.32 + 102.4π =
**14 236.019087727595 mm³**, 17 faces, 42 edges.

**Method.** Native container-free stack on isolated ports (gateway :8010,
documents :8011, geometry :8012, Vite :5199; fresh SQLite via
`metadata.create_all`). Playwright in a real browser plus direct API drives.
New probes: `apps/web/e2e/import-remix.spec.ts` (5 tests, desktop + a `hasTouch`
project). Regression slice re-run on the same stack: 46/46 green
(`feature-selection`, `import-step`, `drawing-reanchor`, `repick-face`,
`fillet-edge-pick`, `hole`, `sketch-on-face`, `export`, `preselection`).

**Verdict: PASS on numbers, FAIL on ergonomics.** Every geometric result was
exact — nothing silently wrong, nothing off by a digit, in seven independent
closed-form comparisons and an export round trip. But the flow the scenario
names is not actually completable in the UI: you cannot put a hole where you
want it on an imported face, and you cannot locate a sketch against imported
geometry at all. One measured consequence was a part 0.065 mm out of
concentricity with every number on screen correct.

### The numbers (app vs closed form, to the digit)

| step | app returned | closed form | Δ (mm³) |
|---|---|---|---|
| import as authored | 14 236.019087727622 | 13 914.32 + 102.4π | +2.7e-11 |
| + 5th Ø3 through hole | 14 179.470419963 | prev − 18π | +3.1e-11 |
| + Ø30/Ø10 × 4 register ring | 16 692.744542835 | prev + 800π | +1.5e-11 |
| + 1 mm chamfer, ring OD | 16 646.667850582 | prev − (44/3)π *(Pappus)* | −1.6e-10 |
| vendor **rev B** (8 → 10 thick) | 20 012.087683200 | 17 392.9 + 833.71333π | +2.9e-11 |
| vendor **rev C** (chamfer 5 → 6) | 16 470.667850582 | 13 738.32 + 869.73333π | 0 (12 s.f.) |
| STEP export → re-import | 16 646.667850582 | identical | −2.0e-10 |

The chamfer row is the interesting one: a 1 mm × 45° chamfer on a circular edge
of radius 15 removes, by Pappus, `0.5 · 2π · (15 − 1/3)` = **46.076692253 mm³**;
the app removed **46.076692253 mm³**. Topology held throughout: 17/42 on
import, 24 faces / 57 edges after the remix, and 24/57 again after the
export → re-import round trip.

**Rev B and rev C are the headline strength.** Patching the import feature's
STEP payload in place re-anchored ALL FIVE downstream remix features — a hole
on a signature-matched face, a datum on that face, a sketch on the datum, an
extrude, and a chamfer on a circular edge — with the volume exact to twelve
significant figures and identical topology. That is the hardest thing in this
scenario and it works.

**glTF face ordinals, both encodings.** For the remixed body, every one of the
18 glTF face ordinals resolves to the same B-rep face as `body.faces()[N]`:
per-face mesh area matches the exact B-rep area to ≤4.1e-4 relative, and the
area-weighted mesh centroid matches the GProp mass centroid to **0.0000 mm** on
all 18. On the fused side, an 11-face milled plate arrives in 6 primitives and
the viewport recovers all 11 (`data-total-faces` = 11). No ordinal slip in
either codec.

### QA3-1 — P1 · the Hole command cannot place a hole where you need one

`HolePointOverlay` offers exactly two placements: the face's **area centroid**
("Centre of face") and the face's **corner vertices**. `hole-position` is a
read-only readout; its "Change" button re-arms the same two-choice pick. There
is no numeric entry and no snap to the body's own circles or edges.

On this plate the seeded centroid is inside the Ø5.2 shaft bore, so the default
action fails, and the only alternatives are the eight octagon corners. **Adding
a 5th mounting hole to this vendor plate is therefore impossible through the
UI.** (The 5th hole in every number above was authored through the API.)

Repro — `import-remix.spec.ts` "the Hole command's seeded point on a bored
plate fails HONESTLY": import the fixture → Hole → pick the z = 0 face → drill.
Result `hole_off_body`, last-good body preserved. The ERROR is exemplary: typed,
per-feature, names the cause, keeps the good body. The message even says "Move
the point onto solid material on the face" — but there is no control that moves
the point. That failure is now pinned as a passing gate, so the day a numeric
position lands the spec goes red and the assertion gets rewritten.

Note the workaround exists and is what a user will end up doing: datum-on-face →
sketch a circle → extrude cut. Which makes the Hole command's own placement gap
the thing to close, not the capability.

### QA3-2 — P1 · a sketch on an imported face has NO reference to the import

Two facts compound:

1. A datum-on-face's plane ORIGIN is the face's **area centroid**
   (`geometry.kernel.faces._face_plane`), which for an asymmetric face is not
   the part origin and not any feature of the part.
2. `apps/web/src/sketch/snap.ts` snaps only to the sketch's OWN entities and the
   grid — never to a body edge, a hole centre, or projected geometry — and there
   is no way to dimension a sketch entity to imported geometry.

So on an imported face you draw in an unnamed frame whose origin is an
accident of the face's outline, with nothing to measure against.

**Measured consequence.** A Ø30/Ø10 register ring drawn at sketch (0, 0) on the
plate's back face — intended concentric with the vendor's shaft bore — came out
**0.065111070 mm** eccentric, because the 5th hole had already shifted that
face's area centroid by exactly

    15.5 · π·1.5² / (1739.29 − 15.76π − π·1.5²) = 0.065111070 mm

Prediction and measurement agree to nine decimals, so the mechanism is certain.
A motor register is a ±0.02 mm feature: that is a scrap part. Every number the
app reported about it was correct — the volume, the area, the extents, the
centroid — and nothing on screen said the ring was off the bore axis.

Not P0 only because the app faithfully built what was specified; the defect is
that there is no way to specify what was meant, and no way to see the error.

### QA3-3 — P2 · selecting a hole lights the whole plate

Selecting the 5th hole lights 3 faces of 18 — its Ø3 wall (75.4 mm²) plus the
plate's entire top (1 323.8 mm²) and back (1 682.7 mm²) faces, because the bore
re-cut both. On screen the "feature-localized" highlight reads as *this Ø3 hole
owns the vendor's entire top surface*. Fusion and SolidWorks light the bore wall
and its edges, not the host face.

This is the documented rule working as written (`provenance.py`: the earliest
feature after which the face exists in its FINAL form), but it defeats the
purpose FINDINGS #9 states — "highlight ONLY a selected feature's faces … instead
of clay-swapping the whole part" — on any part where a small cut meets a large
face, i.e. every real part. Worth a rule that distinguishes a face a feature
CREATED from one it merely re-bounded.

`feature-selection.spec.ts` cannot see this or any regression near it: it asserts
only `0 < lit < total` and `litA !== litB`, which 3-of-18 satisfies whatever the
3 are. `import-remix.spec.ts` asserts the exact counts (3 / 15 / 18 imported,
6 / 5 / 11 fused) against closed-form topology instead.

### QA3-4 — P3 · the published overlay contract is stale after PERF-4b

`OverlayFace.feature_id`'s description (py-kit → `packages/contracts/
gateway.openapi.json`, so it is the PUBLISHED interface) still tells clients
"each face's `index` is its `body.faces()` ordinal (== the GLB primitive ordinal,
one glTF primitive per B-rep face)". Since `d8a4126` that equality holds only on
the unfused encoding; below 12 triangles/face the ordinal must be recovered from
`extras.LOFT_face_triangles`. The web app does this correctly; a third-party
client written to the contract would mis-highlight on every sparse part.
Measured: 11 B-rep faces arriving in 6 primitives.

### QA3-5 — P3 · small features are tessellated ~200× finer than asked

Every cylindrical face gets **126 circumferential segments regardless of
radius** — the angular criterion is radius-independent and swamps
`DEFAULT_LINEAR_DEFLECTION = 0.1 mm` on anything smaller than ~20 mm. Measured
max chord error on the remixed plate:

| feature | r (mm) | tris | max chord error | vs the 0.1 mm budget |
|---|---|---|---|---|
| Ø3 mount hole | 1.5 | 252 | 0.000467 mm | 214× finer |
| Ø5.2 shaft bore | 2.6 | 252 | 0.000808 mm | 124× finer |
| Ø10 ring bore | 5.0 | 252 | 0.001554 mm | 64× finer |
| Ø22 pilot boss | 11.0 | 252 | 0.003419 mm | 29× finer |

The 24-face remixed plate meshes to **4 846 triangles**, ~1 500 of them in six
cylinders totalling under 6 cm². It also pushes such a part to 202 triangles per
face, well past PERF-4b's threshold of 12, so it declines the fusion that would
otherwise have removed its 24 primitives of JSON. A real vendor STEP with a
hundred tapped holes pays this on every hole.

### QA3-6 — P3 · `data-camera-pos` reads like a live camera hook and is not

It is stamped only on a programmatic view SETTLE (fit / view command), never on
a user orbit or pan. A touch-orbit probe that WORKS therefore looks broken —
that cost a false positive here before it was root-caused. `import-remix.spec.ts`
asserts on a canvas raster fingerprint instead. Either stamp it on control
change or rename it to say what it means.

### Friction log — what a working engineer would swear at

1. **You cannot drill where you want.** (QA3-1.) Two placements, both
   accidents of the face's outline.
2. **The sketch has no idea the imported part exists.** (QA3-2.) No projected
   geometry, no snap to a hole centre, no dimension to a model edge. On a part
   you authored you can at least reach back to the sketch that made it; on an
   imported one there is nothing to reach for.
3. **The sketch plane's origin is a moving target.** Add a feature that changes
   a face's outline and every future sketch on that face starts from a different
   point. Nothing names the frame or draws its origin against the part.
4. **One part = one imported body.** A second `import` is a typed 422
   (`import_with_prior_body`) and the toolbar disables with "only the first body
   can be imported". Documented v1 scope, but it means the commonest interop job
   — combine two purchased components into one machined part — has no home in a
   part document.
5. **Selecting a feature EDITS it.** A tree click opens the feature's editor and
   puts the app in command mode, so "show me what this feature owns" and "change
   this feature" are the same gesture; you must Escape before the next command.
6. **The drawing arrives blank of dimensions and mostly blank of sheet.** Four
   views of a 42 mm part on A3 at 1:1 occupy about an eighth of the page, and
   every dimension is a manual edge click. No hole table, no centre marks, no
   bolt-circle callout — the three things a mounting-plate drawing is FOR.
7. **`?format=` is a query parameter** on both export routes while every other
   write takes a JSON body; the mistake costs a 422 whose `loc` is the only clue.
8. **Part names are unique per owner**, so a second "Bracket" is a 409
   (`part_name_taken`) even in a different folder.

### What is genuinely good

* Vendor-revision swap re-anchoring (rev B and rev C, five downstream features,
  exact to 12 s.f.). Nothing in the scenario is harder.
* Every error on the unhappy path was typed, per-feature, named its cause, and
  preserved the last-good body. Not one 500, not one silent wrong solid.
* STEP + STL + a four-view A3 drawing + PDF/DXF/SVG all come out the other end
  for a part whose base body was imported, with the document's name on the file.
* Touch: one-finger orbit works on the imported body and the face census is
  identical to desktop.

---

## 2026-07-30 — wave review of the day's ~20 commits

**Method.** Native container-free stack on isolated ports (gateway :8070,
documents :8071, geometry :8072, Vite :5193; fresh SQLite files). Playwright
against that stack in two projects, `desktop` (1600x1000) and `touch`
(hasTouch, same viewport). New probes live in
`apps/web/e2e/qa-wave-0730.spec.ts`; the four defects below are pinned there as
`test.fail()` gates, so each one flips the suite RED the day it is fixed — that
is the signal to delete the marker.

**Verdict: FAIL.** Four defects, one of them a silent wrong solid. Six probes
pass on both projects, and the regression sweep is clean (63 shipped specs).

### QA-1 — P0 · a body-scope mirror WELDS a void that straddles the plane

The reflection fills the void instead of reflecting it, every feature reports
`ok`, and the body OCCT itself calls invalid is tessellated, measured and
exported.

Repro (API or UI, same result — `qa-wave-0730.spec.ts` "G"):

1. Sketch a 40x40 rectangle on XY; extrude 10 mm, `add`.
2. Sketch on XZ: a construction line `(8,-5)-(8,20)` plus a rectangle
   `x 12..16, y 2..10`.
3. Revolve that profile 360° about the construction line, `operation: cut` —
   an annular groove centred on the XZ plane. Body = **15,396.8142 mm³**
   (= 16,000 − π·192, exact).
4. Mirror, `plane: XZ`, `scope: {kind: body}`.

| | value |
|---|---|
| observed | **31,865.9587 mm³**, 12 faces, `Shape.is_valid` **false** |
| expected | **30,793.6284 mm³** (= 2 × 15,396.8142 = 32,000 − π·384) |
| error | **+1,072.330 mm³ — 3.48 % too much material**, silently |

Two controls prove it is the mirror and not the model:

- the same final solid built DIRECTLY (an 80-long block with the full ring cut)
  gives **30,793.6284** — the analytic value, 11 faces;
- the same chain with the ring moved CLEAR of the mirror plane (axis at x = 20,
  mirror about YZ) gives a ratio of **2.0000000000000004** — correct.

Root cause, traced in-process:

```
PATH: mirror_cut   ntools=1  tool volume 1206.3716
  reaches body?  False          -> MirrorUnreachableError -> mirror_union
  FUSED volume   30793.628421021516
  CLEANED volume 31865.95871344683      <- clean() inflates
```

Because the cut is already in the body, `removal_reaches_body` is False and
`mirror_cut` falls back to `mirror_union`, whose `fuse` + `clean()` weld the two
half-voids shut. (In a pure build123d repro of the same revolved ring the `fuse`
itself already returns 31,865.9587 with `is_valid` false, so the inflation moves
between `fuse` and `clean` with the shape's provenance — either way the result
is invalid and **nothing in the pipeline checks it**.)

**Regression from `6c9c432`** ("a body-scope mirror after a revolve/sweep/loft
cut filled the void it should have reflected"). That commit closed the
tool-recording half of CM-5. The straddling-void half is still open, and it
fails the same way, through a different door.

### QA-2 — P1 · changing a plate's thickness destroys every hole on its face

The commonest revision in CAD. It TRANSLATES the top face, and the picked-face
reference is resolved by absolute centroid, so the hole drilled in that face is
lost and everything after it is stranded.

Repro (`qa-wave-0730.spec.ts` "A", second test):

1. Build: 60x40 sketch → extrude 10 `add` → Ø6 through hole on the top face
   (signature `area 2400, centroid (30,20,10), normal +Z`) → linear pattern
   x3 @ 60 → mirror about XZ → fillet R1 on all edges. Solves,
   **142,020.953 mm³**, exports a clean STEP.
2. Select Extrude1, retype the distance 10 → **16**, Enter.

| | observed | expected |
|---|---|---|
| Hole1 | `subshape_unresolved` — "No planar face of the current body matches the stored face signature" | ok |
| Pattern1 / Mirror1 / Fillet1 | `skipped` | ok |
| body | **38,400 mm³** — a featureless 60x40x16 brick | ≈ 227,000 mm³ |
| STATUS / EXPORT | `Partial` / blocked | `Up to date` / `Ready` |

The face is the SAME face by every invariant except position: same area (2400),
same normal, same plane orientation, translated z 10 → 16. `7fde5d2` states a
picked face "has had a two-tier matcher since FINDINGS #3 … a resilient re-match
on the strongest invariant alone"; that tier does not survive a translation,
which is exactly what a depth edit does to every face on the far side. The
product audit's "revision wall" is therefore still standing for holes.

### QA-3 — P1 · a diameter dimension the revision never touched is destroyed

Repro (`qa-wave-0730.spec.ts` "B", second test):

1. 40x25 sketch with a Ø10 circle → extrude 10. Create a drawing, select the
   part, auto-lay-out the four standard views.
2. Pick the hole's circle in the TOP view → Diameter. Sheet stamps `Ø10.000`.
3. Back to the part; retype Extrude1's distance 10 → 16. Re-project the drawing.

| | observed | expected |
|---|---|---|
| Dimensions panel row | `diameter · unresolved` | `diameter · Ø10.000` |
| the sheet | annotation **gone** | `Ø10.000` |

The hole's diameter did not change — only the plate's depth did. The circle's
tier-2 re-anchor ("centre plus angular station") keys on the 3-D centre, which a
depth change translates in z.

Worth stating plainly, because it is the good half of the same test: the LINEAR
dimension on the thickness edge **did** follow the edit, `10.000 → 16.000`. The
N1 line fix works. Incomplete rather than wrong: **`7fde5d2`**, one curve kind
over.

### QA-4 — P1 · a lost dimension leaves NO trace on the print

Same repro as QA-3, then export.

| surface | observed | expected |
|---|---|---|
| exported `.svg` | no `REFERENCE LOST`, no marker, no annotation | `DIAMETER DIM: REFERENCE LOST - RE-PICK THE EDGE` |
| on-screen sheet | nothing | the same caption |
| Dimensions panel | `unresolved` | (correct — but it is a side panel, not the drawing) |

`7fde5d2`'s own account: "A reference that genuinely cannot be re-anchored now
prints WORDS beside the view … in SVG/PDF/DXF", implemented at
`drawings/compose.py::_DIM_ERROR_PHRASE` / `dimension_error_caption`. On this
path nothing is stamped on either surface, so a shop receives a print that has
silently lost a dimension and looks complete. (Whether the web never forwards
the unresolved dimension to the composer, or the composer declines to stamp it,
is for the builder — QA measured only that neither surface says a word.)

### Verified good — the probes that passed, desktop AND touch

- **Rollback + export together.** Before the click the strip carries
  `data-export-state="partial"` and a sentence saying the file will be marked
  partial; the download's filename contains `-partial` and the content is real
  ISO-10303-21. `TO TIP` returns the strip to `ready` and the next filename is
  clean. (`b4e075f`, `1a27804`.)
- **A failed feature reads the same on five surfaces.** SOLVE `Failed`, STATUS
  `Partial` + "Hole1 failed · built to Extrude1", the tree's error row carries
  `hole_off_body` with the friendly sentence, the viewport notice repeats it,
  the export gate is `feature-error` and a FORCED click on the gated cell
  produces no file — and the **parts register next door** agrees
  (`part-health data-health="failed"`, "Broken"). The one cell `partBuild.ts`
  does not reach was the one worth checking, and it holds.
- **Undo/redo across the timeline.** Chips 3 → 2 → 3 across undo/redo; the stop
  reports `aria-valuetext "After Extrude1 — 2 of 3 built"`; after an undo that
  removes the tip feature the stop stays inside `aria-valuemax`, so it never
  points past the end of the tree.
- **The shell refusal reaches the user.** t = 2 on the SH-1 4 mm rib gives
  `shell_thickness_too_large` in the tree with the whole actionable sentence
  ("…an internal wall of this body is exactly 4.0 mm thick … Change the
  thickness so it is not exactly half that wall — a little thinner leaves a thin
  cavity…"), and the last-good body is untouched at **14,400 mm³** with STATUS
  "built to CornerFillets". (`5af2f6b`.)
- **Materials report absence, not zero.** With no material assigned,
  `properties.mass_g` and `properties.center_of_mass` are `null`, and each
  `bodies[]` entry carries `material: null, mass_g: null`. Never `0`.
  (`78ad8a4`.)
- **Services fail closed on default datastore credentials.** With `LOFT_ENV`
  unset, `POSTGRES_URL=postgresql://loft:loft-dev-only@db:5432/loft` raises
  naming the variable, the defect and both remedies; an empty password likewise;
  `LOFT_ENV=dev` warns and boots. (`c695b11`.)
- **Regression sweep clean.** 39 shipped specs on desktop (drawings,
  drawing-sheets, drawing-place-view, shell, mirror, undo-redo, full-flow,
  export, p2-register-health, preselection, repick-face) and 24 on touch
  (viewport-gestures, timeline, body-status, sketcher, parts-home) — all pass.

### Observations (not defects)

- `shell_thickness_too_large` has no entry in
  `apps/web/src/features/featureErrors.ts`, so the raw server message is what a
  modeler reads. It happens to be excellent; noting it only because the friendly
  table is where that guarantee is supposed to live.
- Nothing in `apps/web` imports `src/api/materials.ts`, and the body inspector
  has no mass row — mass is API-only today, so "MASS PROPERTIES can report mass"
  is true of the service and not yet of the panel named in the sentence.
- The credential guard is an allowlist (`KNOWN_DEV_CREDENTIALS`), so a password
  equal to the project's own name (`loft:loft`) passes. Correct as scoped —
  worth knowing before someone reads it as an entropy check.
