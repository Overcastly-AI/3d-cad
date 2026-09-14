# Design direction — Redesign Wave 3: the numbers have handles

**Date:** 2026-09-13 · **Author:** frontend-qa (design direction, pre-build)
**Status:** DECIDED. Five builders implement against this; it is not a menu.
**Audited against the running app** — native stack on :8100/:8101/:8102, Vite
:5311, real Chromium at 1280×800 and 1600×1000 — not against the source and not
against imagination. Reference frames: `docs/design/screenshots/w3-direction/`.

Every claim below is marked **MEASURED** (I drove it in the browser or computed
it from the shipped constants) or **PROPOSED** (a decision I am making, which a
builder may not silently re-litigate but may escalate with evidence).

**The sentence a user says if this wave works:** *"I stopped typing numbers into
a form and started pulling the shape."*

---

## 0. The one-paragraph version

**The handle exists, it works, and almost nobody can grab it.** The extrude
gauge ships today and is good: an arrow on the profile, a snapping drag, a real
`role="slider"` with arrow-key stepping, a readout at the tip. Its hit region is
a **24 × 24 px dot at the very point of the arrow** — measured, **2 of 16
sample points along the drawn axis are hittable**, and a real `page.mouse` drag
on the middle of the shaft does *nothing at all*. So W3's foundation is not an
invention, it is a **generalisation plus a repair**: make the drawn instrument
the target, make the on-geometry number typeable, lift the whole thing into one
primitive with three *tracks* (linear, angular, stepped), and apply it to the
six verbs that today have no viewport affordance of any kind. Every decision
below exists to stop five agents shipping five drag grammars.

---

## 1. Ground truth — what actually ships, measured

### 1.1 The correction that has to come first

`CLAUDE.md`'s design mandate says, in the sentence three briefs have now quoted:

> *"Ours is a form with no handle at all — the single biggest 'does not feel
> like a modeling tool' gap we have, bigger than any missing feature."*

**That sentence is stale.** It predates T-23, which shipped
`apps/web/src/viewport/ExtrudeDragHandle.tsx` (601 lines) and
`extrudeHandle.ts` (442 lines), with `extrude-drag-handle.spec.ts` driving the
real gesture. The roadmap's own CRAFT-7 row ("**fix** the extrude grip") is the
accurate one. A builder handed both will waste a day deciding which to believe;
this section is the answer, and the durable form of it is: **the gap is not
absence, it is reach.**

I am not editing `CLAUDE.md` (not my territory). Flagged for the orchestrator
in §11.

### 1.2 The hit-region measurement — the most important number in this document

Sampled 16 points evenly along the gauge's projected axis at a 40 mm extrude,
`document.elementFromPoint` at each, 1280 × 800:

| t along axis | 0.000 → 0.867 (14 points) | 0.933 | 1.000 |
|---|---|---|---|
| resolves to | `canvas` / `viewport` | `div` / `extrude-depth-handle` | `span` / `extrude-depth-handle` |

**2 of 16. The last 13 % of the axis, which is the 24 × 24 grip box and nothing
else.** Grip box measured `{x: 638.3, y: 363.9, w: 24, h: 24}`; the axis spans
101 px, so the reachable band is 24 px of 101.

Then the gesture a modeller actually makes — press on the middle of the drawn
arrow and pull:

```
mouse.move(mid) → mouse.down() → mouse.move(mid.y - 60, steps 6) → mouse.up()
AFTER SHAFT DRAG distance = 40      (unchanged; it was 40 before)
```

**MEASURED: the drawn arrow is inert.** The shaft, the arrowhead cone and the
ladder are WebGL with no raycast target; only the drei-`Html` dot is a control.
This is the repo's own zero-area defect family (an SVG stroke that
`getBoundingClientRect` ignores; an `sr-only` element every visibility API calls
visible; a Tailwind class that was never generated) wearing a **fourth** costume:
**a manipulator drawn in GL with its target in the DOM, where only the target
is a control and only the drawing is visible.** The two are 90 px apart at the
default depth and nothing says so.

Why this is worse than either half alone: the one place you *can* grab is the
place that looks *least* like a handle — a 12 px collar at 40 % opacity
(`rgba(227,166,75,0.4)`, measured) sitting on the point of an arrow that is
itself drawn at 92 %. The affordance and the target are anticorrelated.

### 1.3 Every other verb has nothing

Opened each editor on a seeded 20 mm cube and swept the DOM for
`[role="slider"]` and `[data-testid*="handle|gizmo|drag|grip"]`:

| verb | sliders found | handles found |
|---|---|---|
| fillet, chamfer, shell, revolve, pattern, hole | `["timeline-stop"]` (the history scrubber) | `[]` |
| draft | *n/a — `new-draft` is disabled on a plain cube* | — |

**MEASURED. Six verbs, zero affordances.** CRAFT-9/10/11 are greenfield, not
repairs.

And the harder fact underneath it: **`ExtrudePreview` is the only live ghost in
the entire product.** Grepping every preview test-id across `apps/web/src`
returns exactly two: `extrude-preview-active` and `corner-relief-size-preview`.
The fillet screenshot shows a radius of 2 mm in a rail 900 px from a cube that
is not rounded, not highlighted, not annotated —
`w3-before-fillet-1280.png`. **A gauge with no ghost is a handle attached to
nothing**, and a handle whose drag produces no change in the model is a
*worse* lie than a form. This constrains CRAFT-9/10/11 hard; see §9.

### 1.4 The gauge's own proportions are governed by two unrelated scales

Computed from the shipped constants (`extrudeHandle.ts`), then confirmed against
`w3-before-gauge-rest-1280.png` and `w3-before-gauge-hover-1280.png`:

* **Head length** = `min(18, max(2, 0.25 × profileRadius))` — from the
  **profile**.
* **Shaft length** = the depth — from the **value**.

So the head exceeds the shaft whenever `depth < arrowLength(radius)`:

| profile | radius | head | head > shaft for any depth below |
|---|---|---|---|
| 100 × 60 | 58.3 mm | **14.58 mm** | 14.58 mm |
| 200 × 120 | 116.6 mm | **18.00 mm** | 18.00 mm |
| 40 × 25 | 23.6 mm | 5.90 mm | 5.90 mm |

**The default extrude distance is 10 mm.** So on any plate-sized profile the
product's flagship manipulator opens *head-heavy* — more than half its drawn
length is arrowhead. That is exactly what the rest crop shows.

### 1.5 The signature element is illegible at the default state

The ladder is the one place the gauge spends boldness (`tokens.ts` says so in
its own words). Its **pitch** comes from the depth (1/2/5 decade series, ≤ 12
rungs); its **cross half-width** comes from the profile
(`LADDER_HALF_WIDTH_FRAC = 0.18 × radius`). The two are unrelated. Computed on a
58 mm-radius profile:

| depth | rungs | pitch | cross width | width ÷ pitch |
|---|---|---|---|---|
| 5 mm | 9 | 0.5 mm | 21.0 mm | **42 ×** |
| **10 mm (default)** | 9 | 1 mm | 21.0 mm | **21 ×** |
| 20 mm | 9 | 2 mm | 21.0 mm | 10.5 × |
| 40 mm | 7 | 5 mm | 21.0 mm | 4.2 × |
| 100 mm | 9 | 10 mm | 21.0 mm | 2.1 × |

A scale whose marks are **21 times wider than they are apart** is a hatch, not a
scale. The hover crop shows it: brass crosshatching over the arrowhead, reading
as debris. **The graduations only begin to resolve at ~100 mm on that profile**,
which is 10 × the default. MEASURED by arithmetic, confirmed visually.

This matters more than it looks: mandate 3c says a chrome element that only
decorates is a defect. Right now the ladder decorates.

### 1.6 Keyboard and exit behaviour, measured from the focused grip

| gesture | result | verdict |
|---|---|---|
| press `5` | **nothing at all.** `distance` stayed `10`, `aria-valuenow` stayed `10`, focus stayed on the grip, no editor change | FB-16 gap — the sketcher captures digits at draw time (`drawDimensionKeys.ts`), the gauge discards them |
| `Tab` | focus → **`view-home`** (a view-rail button) | the "precision fallback" is not one key away; it is across the frame |
| `Escape` | the whole command cancels (`extrude-editor` count 0, feature rows 1) | correct and matches the band's `CANCEL ESC` — but there is no *inner* thing for Escape to undo, so a drag cannot be abandoned |
| `Enter` | commits via `requestSubmit()` | good; keep |
| arrows / Shift+arrows / Page | step on their own grid, announced via `aria-describedby` | **genuinely at the bar.** Do not touch |

### 1.7 The value round-trip, and why it is a hazard worth a primitive

MEASURED by reading the wiring:

```
gauge onDepthChange(mm)
  → PartPage  setExtrudeDragDepth({mm})        (1684, 1687)
  → ExtrudeEditor  depthOverride prop          (5151)
  → form.distanceInput = lengthInputValue(...) (ExtrudeEditor 165-171)
  → onPreviewChange → PartPage extrudePreview  (5151)
  → <ExtrudePreview distanceMm> → gauge value  (5522)
```

Six hops, several renders. `ExtrudeDragHandle` carries ~60 lines of an
**optimistic ask-queue** to survive it — written after two quick taps of `Up`
produced 10.5 instead of 11, intermittently, under load. That code is correct
and hard-won. **Four more copies of it is four more chances to reproduce a
lost-update bug whose only symptom is an occasional wrong number.** That, and
not tidiness, is the argument for CRAFT-8.

### 1.8 What is already in `packages/design` and does not need building

* **`AxisGrip`** — `role="slider"`, 24 px constant target, rest/hover/focus/grab
  states, `motion-reduce:transition-none`. Keep.
* **`DimensionTagCell` already has BOTH states**: `readout` (text, inert) and,
  with `readout` omitted, **a real `<input inputMode="decimal">`** with
  focus-within brass ground. **CRAFT-7's "the tag becomes an input" needs no new
  primitive** — it is dropping one prop and wiring two. MEASURED by reading
  `DimensionTag.tsx`; the docstring already states the two-state contract.
* **`proposal` tokens** — chip width 120, `offset: 14`, and the two-tone leader
  stub geometry in `ProposalNote.tsx`. The gauge's tag should borrow the leader;
  see §2.

### 1.9 One DRY finding that lands squarely on CRAFT-10

There are **three** angle formatters in app code and **none** in
`packages/design`:

| where | behaviour |
|---|---|
| `measure/geometry.ts: formatAngleDeg` | `toFixed(1)` + `°`, `"—"` for null |
| `features/revolve.ts: formatAngleInput` | `String(angleDeg)` |
| `features/hole.ts: formatAngle` | integer, else `toFixed(2)`, no suffix |

An angular gauge written against any of them makes a fourth. `formatLength`
lives in `packages/design/src/units.ts`; `formatAngle` belongs beside it, and
CRAFT-8 is the only item in the wave that may touch that file. See §6.

---

## 2. DECISION 1 — the grammar. The gauge is idiom **D**, and W3 extends it

W2's direction inventoried three "the app is telling you something" idioms and
made a law: *nothing may add a fourth*. That law was about **notices**. The
gauge is not a notice — it is an **instrument**: a thing you take hold of. So
the inventory gains one row, and the law gains one line, and then it is closed
again.

| # | idiom | means | vocabulary |
|---|---|---|---|
| A | Leader note (`ProposalNote`) | *"here is a verb you can take right now"* | anchor dot + two-tone stub + brass chip + `Kbd` |
| B | Cursor mark | *"this is the name of the thing under your pointer"* | mist chip, no leader, no `Kbd`, inert |
| C | Band state cell | *"a selection is held and it renames these verbs"* | eyebrow + value + `×` |
| **D** | **Instrument (the gauge)** | ***"this number is a thing you can pull."*** | **brass line-work drawn on the geometry + a grip you take + a drafting tag carrying the number, tied to the grip by a leader** |

**The law, now four lines. Put it in the primitive's docstring:**

- brass + leader + `Kbd` = an offer you can take right now. (A)
- mist + no leader + no `Kbd` = a name for what is under the pointer. (B)
- band cell + eyebrow + `×` = a held state that renames verbs. (C)
- **brass line-work + grip + graduations = a value you can pull.** (D)

**Nothing in W3 may add a fifth.** A gauge that only displays a number is idiom
B wearing brass, and is the decorative-chrome defect mandate 3c names.

### 2.1 The instrument at rest, hover, and drag — exact

PROPOSED, and this is the one place the wave spends boldness.

| state | drawn instrument | grip collar | ladder | tag | cursor |
|---|---|---|---|---|---|
| **rest** | `manipulator.axis` @ `axisOpacity` (0.92) | **none** | none | `readout`, brass-on-anvil, **leader stub to the grip** | `grab` over the sleeve |
| **hover** | `manipulator.active` | 12 px collar, full accent | **visible** | unchanged | `grab` |
| **focus (kbd)** | `manipulator.active` | collar + `focus-visible` brass outline | **visible** | unchanged | — |
| **drag** | `manipulator.active` | collar + filled core | **visible** | tag value tracks the pointer | `grabbing` |
| **typing** | `manipulator.active` | collar | **visible**, with the typed value's rung marked | tag is an **input**, caret in it | `text` |

**Remove the rest-state collar.** Chanel's rule, applied with a reason: at rest
there are two brass rings claiming to be the affordance — the arrowhead and the
collar — and the collar is the weaker of the two at 40 % opacity while being the
only one that works. Once the whole drawn arrow is the target (§9, CRAFT-7), the
arrow *is* the affordance and the collar at rest is a second accessory saying
the same thing more quietly. It returns the instant the pointer or the keyboard
addresses the gauge, which is when "you are on it" is new information.

**Give the tag a leader.** MEASURED: today the tag is placed by a bare CSS
offset (`-translate-y-8 translate-x-4`) and floats unattached —
`w3-before-gauge-rest-1280.png` shows `D 10 mm` hanging in space with no tie to
the arrow. Idiom A already owns the answer: an anchor dot on the point the note
is about, a two-tone hairline stub, the card at the end. **Reuse
`ProposalNote`'s leader geometry and its two-tone stub.** This is the single
cheapest move in the wave that makes the gauge belong to the app's own language,
and it stops the tag reading as a floating HUD chip. The anchor dot goes on the
grip; the stub goes up-and-out; the tag hangs off it.

**Do not animate anything.** No fade-in, no pulse, no spring. The existing
components have no entry animation and say why. `prefers-reduced-motion`
therefore needs no new code beyond the `motion-reduce:transition-none` already
on `AxisGrip`'s colour transition — state that in the commit rather than
omitting it, so the next audit can tell "honoured" from "never considered".

### 2.2 Proportion — fix the two-scale problem

PROPOSED. Both defects in §1.4 and §1.5 have the same root: **two lengths
derived from two unrelated quantities.** The rule:

- **The arrowhead is bounded by the shaft it terminates.**
  `headLength = clamp(0.25 × profileRadius, 2, min(18, 0.45 × value))`. A head
  may never be more than ~45 % of the drawn shaft, so the instrument always
  reads as *a rod with a point on it* rather than *a cone on a stub*.
- **The graduation cross is bounded by its own pitch.**
  `halfWidth = min(0.18 × profileRadius, 0.4 × pitch)`, floor 2 mm. Width ÷
  pitch then never exceeds 0.8, at any depth, on any profile — the table in §1.5
  becomes a column of `≤ 0.8`.

Both are pure arithmetic inside the primitive, both are unit-testable without a
browser, and both belong in CRAFT-7 (they move pixels; CRAFT-8 may not — §8).

---

## 3. DECISION 2 — the snap ladder

### 3.1 The thesis: the drawn rungs ARE the stops

PROPOSED, and it is the wave's sharpest design decision.

Today the ladder and the snap are **two different ladders**. The rungs come from
a 1/2/5 decade series chosen for display; the snap comes from
`SNAP_MM = {mm: 0.5, in: 1/32}`, a constant. At the default 10 mm extrude the
user sees rungs 1 mm apart and the drag stops every 0.5 mm. **The scale you can
see has nothing to do with what the drag does**, which is the decorative-chrome
defect in the one element the roadmap calls the signature.

**Decision: unify them. The rungs the gauge draws are exactly the values the
drag snaps to.** This does three things at once — it makes the signature
functional, it tells the user what the snap will do *before* they drag, and it
kills the width-vs-pitch problem because one ladder can be chosen for legibility
and the snap simply follows it.

### 3.2 What snaps, at what zoom

PROPOSED.

- The ladder is chosen from the **1/2/5 decade series**, as today, but with an
  added **screen-space floor**: the step is raised until the projected pitch is
  **≥ 14 px** at the current camera. 14 px is the repo's own dense-target half
  (`target.dense = 24`) and is the smallest pitch at which two crosses read as
  two marks in the captures I took.
- **This makes the snap zoom-aware, which is the answer to the brief's "at what
  zoom".** Zoom in and the ladder subdivides — 5 mm → 2 mm → 1 mm → 0.5 mm — and
  the drag snaps finer with it. Zoom out and it coarsens. That is Fusion's and
  Plasticity's behaviour and it is *why* their drags feel precise without a
  settings panel: precision is a function of how closely you are looking.
- **Major / minor.** Every rung at a decade multiple is drawn full-width at
  `ladderOpacity`; intermediate rungs are drawn at **60 % of that width** and
  `ladderOpacity × 0.6`. This is the drafting convention and it removes "which
  of these nine identical crosses matters". A coarse (Shift) key press lands on
  a **major** rung; a fine press lands on any rung. The key stepping already
  works this way (`steppedDepth`) — the ladder just stops hiding it.
- **Floor and ceiling.** Never fewer than 3 rungs (below that it is not a scale,
  and the instrument falls back to no ladder rather than showing two marks);
  never more than `LADDER_MAX = 12`, unchanged.

### 3.3 Getting a non-snapped value

Two ways, both already in the app's grammar, and **no third**:

1. **Hold `Ctrl`/`Cmd` while dragging.** Already the sketcher's modifier for
   "ignore the snap" (`SketchScene`'s modifiers) and already the gauge's
   (`quantizeDepth(raw, unit, free)`). The gesture transfers; it is not learnt
   twice. While held, the ladder **dims to 40 %** so the user can see that the
   stops are off — a modifier with no visible consequence is a modifier nobody
   trusts.
2. **Type it** (§4). A typed value is never snapped.

A free drag lands on something like 12.4713, and the first arrow press after it
puts you back on a rung — `steppedDepth`'s "next multiple in the direction
pressed" already guarantees that and its docstring argues it well. Unchanged.

### 3.4 Angular snaps are NOT the linear ladder rotated

PROPOSED, and it is exactly the trap the brief warns about. A builder extending
the linear ladder to CRAFT-10 naively gets **10° / 20° / 50°**, which no
machinist uses and no CAD tool offers.

- **Angular ladder: major 15°, minor 5°.** With a screen-space floor as above,
  the sequence coarsens to **30° then 45° then 90°** and subdivides to **1°**,
  never to a decade series.
- **`Ctrl` frees it, as linear.**
- **360° and 0° are hard stops, not rungs** — a revolve's angle is already
  constrained to `(0, 360]` by `parseAngleDeg`, and a drag that can reach an
  unsubmittable value is the dead-end the flow rule's fourth test forbids. Same
  reasoning as `MIN_DEPTH_MM = 0.1`; reuse it, do not re-derive it.

### 3.5 Count has no ladder because every value is a stop

An integer count is already quantised by its own nature. The **stops** for a
`stepped` track are the instance positions, and they are drawn as the ghost
copies themselves — there is no separate scale to draw. `Ctrl` does nothing on a
stepped track, and the primitive must say so rather than silently ignoring it.

---

## 4. DECISION 3 — the precision fallback: how a drag hands off to typing

The mandate: *"the numeric field is the precision fallback"*. Today it is 800 px
away in the rail and `Tab` from the grip goes to `view-home` (MEASURED, §1.6).
This is where FB-16 and FB-13 both bite, so the rules are stated as absolutes.

### 4.1 The three routes to a value, and they all end in the same cell

PROPOSED.

| route | gesture | lands in |
|---|---|---|
| **coarse** | drag the instrument | the tag's cell, snapped |
| **stepwise** | arrows / Shift+arrows / Page on the focused grip | the tag's cell, on the pressed key's grid |
| **exact** | **type a digit or `.` while the gauge is live** | the tag's cell, caret after the character |

**The third row is the whole decision, and it is not new — it is
`drawDimensionKeys.ts` applied to a second surface.** The sketcher already
promises *"type a digit anywhere and it goes in the first cell"* from the instant
a shape is placed, and FLOW-A1 paid for making that true down to the 27 ms mark.
The gauge discards digits today. **Make the gauge honour the same promise, with
the same module's state machine where it fits and the same rule where it does
not.**

Concretely:

- While a gauge is on screen, a `[0-9.]` keydown that is **not** inside a typing
  target opens the tag's cell with that character in it and puts the caret after
  it. The cell is the **same `DimensionTagCell` that was showing the readout** —
  it drops `readout` and becomes the input it already knows how to be. **The
  number does not move on screen.** That is the single property that makes this
  read as "the readout became typeable" rather than "a field appeared".
- Everything that is not a value character **falls through unprevented**, exactly
  as `drawDimensionKeys` does. The gauge must not swallow the keyboard; `Esc`,
  `Enter` and the verb letters keep working. A gauge that auto-focused its input
  instead would take every key and quietly break the command band's advertised
  keys — the mistake FLOW-A1 explicitly rejected.
- **`Tab` from the grip goes to the tag's cell.** Not to `view-home`. This is
  the keyboard route to precision, and it is one key.
- **`Shift+Tab` from the cell returns to the grip.** The pair is a loop, so a
  keyboard user is never dumped into the view rail mid-command.

### 4.2 `Enter` — one meaning, always

FB-13 is a key that sometimes saves and sometimes discards. The guard is to give
each key exactly one meaning across the whole wave:

> **`Enter` = accept what is in front of you and commit the command.**

From the grip, from the tag cell, from the rail field: `Enter` applies the
pending value and submits, through the **one** existing path
(`useCommandActionStore.requestSubmit`). The grip already does this and its
comment argues it correctly; the tag cell must do the same. **No builder may add
a second submit path.**

For a two-value gauge (hole: depth + Ø), `Tab` moves between the tag's cells and
`Enter` still commits — the same grammar the sketcher's `W × H` strip already
uses. Consistency here is worth more than cleverness.

### 4.3 `Escape` — nested, and it never destroys silently

PROPOSED. Today Escape from the grip cancels the whole command (MEASURED), which
is right when nothing is in flight and wrong when something is.

> **`Escape` undoes the innermost thing you are doing.**

| when | Escape does | then |
|---|---|---|
| a drag is in flight (pointer captured) | reverts to the value the grab started from, releases capture, keeps the command open | a second Escape cancels the command |
| the tag cell is open and edited | reverts the cell to the gauge's value, returns focus to the grip | a second Escape cancels the command |
| nothing inner is open | cancels the command — what the band advertises | — |

Two properties this buys, both of which the flow rule demands: **Escape only
ever discards** (it can never be confused with a save), and **it never discards
more than one level at a time**, so there is always a visible step back before
work is lost. The mid-drag case is not hypothetical: today a mid-drag Escape
cancels the command *with the pointer still captured*, leaving the editor
unmounted under a captured pointer and the eventual `pointerup` going nowhere.

---

## 5. DECISION 4 — one primitive, three tracks. Not three primitives, not one with modes

### 5.1 The split

MEASURED by inventory of what is and is not shared:

| shared by all three (→ the primitive) | differs (→ the track) |
|---|---|
| the optimistic ask-queue and its reconciliation (§1.7) | the drawn track geometry (line / arc / line-with-stops) |
| the DOM grip (`role="slider"`, 24 px, states) | pointer-ray → value projection |
| the hit sleeve along the drawn track | the shallow-axis fallback's screen mapping |
| the drafting tag + leader, readout ⇄ input | the formatter (`formatLength` / `formatAngle` / integer) |
| ladder visibility (hover/focus/drag), major/minor draw | the snap stop set |
| key stepping, `Ctrl` free, `Enter`, nested `Escape` | the clamp range |
| the digit-capture handoff | — |

**Everything in the left column is state and correctness. Everything in the
right column is stateless arithmetic.** That is a strategy split, not a
component split, and it is why one primitive with a `track` parameter is right
and three primitives is wrong: the hard part is identical and the easy part is
not. Three copies of a lost-update fix whose symptom is *an occasional wrong
number* is the worst thing this wave could ship.

Equally, **"one primitive with modes" is wrong** if "mode" means a runtime flag
that changes behaviour inside the component. The track is injected, not
switched: the primitive never branches on `kind`.

### 5.2 The three tracks

```ts
// packages/design — no `three` import; see §6.3 for why these are plain tuples.
export interface GaugeTrack {
  /** World point of the grip at `value`. */
  pointAt(value: number): Vec3;
  /** Pointer ray → value, or null when the track is unaimable from here. */
  valueAt(rayOrigin: Vec3, rayDirection: Vec3): number | null;
  /** Fallback when `valueAt` is null: screen travel → value. */
  screenValueAt(grabValue: number, dxPx: number, dyPx: number, scale: number): number;
  /** Polyline for the drawn track + arrowhead pose, at `value`. */
  draw(value: number, stops: GaugeStops): TrackDrawing;
  /** The snap stops in view, major and minor, at this camera scale. */
  stops(value: number, unitsPerPixel: number): GaugeStops;
  /** Clamp into the submittable range. */
  clamp(value: number): number;
  /** Spoken and displayed form. */
  format(value: number): string;
  /** One fine step, e.g. the minor pitch. */
  step(stops: GaugeStops): number;
}
```

| track | value | geometry | stops | format |
|---|---|---|---|---|
| **`linear`** | length, canonical mm | ray ⟂ axis (today's `depthAlongAxis`), screen-Y fallback below `AXIS_SHALLOW` | 1/2/5 decades, ≥ 14 px | `formatLength` |
| **`angular`** | degrees | ray ∩ the sweep plane, angle about the axis; fallback: tangential screen travel at the arc radius | 15° / 5°, coarsening to 30/45/90 | `formatAngle` (new, §6.4) |
| **`stepped`** | integer | `linear`'s projection, then `round(t / pitch)` | every integer; no `Ctrl` | plain integer |

**`stepped` is `linear` with an integer quantiser, and saying so is load-bearing:
it means CRAFT-11 does not need a new projection, only a new quantiser.**

### 5.3 The pattern gauge: two instruments, not one with two outputs

PROPOSED, and this is the decision the brief flags as the one that makes CRAFT-8
need rewriting halfway if it is got wrong.

The roadmap's sentence — *"drag to set spacing, drag past a pitch to add
count"* — describes **one pointer driving two numbers**, which is exactly the
ambiguity this wave exists to remove. If one drag changes both spacing and
count, the user cannot say which they are adjusting and cannot hold one steady.

**Decision: pattern mounts the primitive TWICE.**

| instrument | track | value | drawn where | stops |
|---|---|---|---|---|
| **count gauge** | `stepped` | instance count | along the pattern direction, from the seed to the last copy | each instance position — a ghost copy appears as the arrow crosses a rung |
| **spacing gauge** | `linear` | spacing, mm | **between the first two instances**, a short gauge across the gap | the linear ladder |

Two grips, two obvious meanings, **no modifier keys**, and the thing you grab
says which quantity you are changing. That is what a real CAD tool does and it
costs nothing extra to build once the primitive exists — CRAFT-11 becomes two
mounts and a ghost, not a new control with a mode.

It also disposes of the roadmap's acceptance criterion cleanly: *"drag changes
`pattern-spacing`; past the pitch increments `pattern-count`"* becomes two
separate, unambiguous assertions.

---

## 6. DECISION 5 — what CRAFT-8 must expose so 9/10/11 never reach back into it

This is the whole argument for a foundation item. If a later item has to change
the primitive, the wave serialises and the foundation was not one.

### 6.1 The component API, complete

```ts
export interface ParametricGaugeProps {
  /** What this drives. Required. e.g. "Fillet radius". Becomes the slider name. */
  label: string;
  /** Terse drafting label for the tag cell — "D", "R", "Ø", "A", "N". */
  tagLabel: string;
  /** The owner's value. The gauge never owns it. */
  value: number;
  /** Ask the owner for a new one. Fires on drag, key, and applied typing. */
  onChange: (value: number) => void;
  /** Geometry + arithmetic. Injected, never switched on. */
  track: GaugeTrack;
  min: number;
  max: number;
  /** Test/query hook shared by grip AND sleeve — see §7.2. */
  gaugeId: string;                       // → data-gauge="<id>" on both
  /** Optional second cell on the same tag (hole depth + Ø). */
  companion?: { tagLabel: string; value: number; onChange: (v: number) => void;
                track: GaugeTrack; min: number; max: number };
  /** Tag placement relative to the grip; default "up-right", flips at the frame. */
  tagSide?: "up-right" | "up-left" | "down-right" | "down-left";
  /** Suppress the tag when another gauge on screen already carries the number. */
  tag?: "leader" | "none";
  /** Announced step sentence; derived from the track if omitted. */
  stepHint?: string;
}
```

### 6.2 The behaviours CRAFT-8 must own, so no later item re-implements them

Every one of these is a thing that would otherwise be written four times:

1. **The optimistic ask-queue** and its reconciliation rules (ack retires the ask
   and every older one; an unrecognised value is a stranger's edit and wins).
   Lift `ExtrudeDragHandle.tsx:165-230` **verbatim** — it is correct and its
   comment is the specification.
2. **Grab-mode selection at pointer-down** (`axis` vs `screen`), including the
   orthographic/perspective `unitsPerPixel` branch. Do not re-derive; ORTHO-1
   already paid for the parallel-projection case.
3. **The hit sleeve** along the projected track (§7.2).
4. **Pointer capture, and its release on cancel** — including release on the
   nested-Escape path (§4.3).
5. **Key stepping** with the pressed key's own grid (`steppedDepth`'s rule),
   fine/coarse, and the `aria-describedby` step sentence with `data-step` /
   `data-coarse-step` attributes on the element so a test can assert the spoken
   step equals the applied one.
6. **Digit capture → tag cell**, with non-value keys falling through
   unprevented, registered through **`lib/modalGate.ts`** (§7.1).
7. **`Enter` → `requestSubmit()`**, one path.
8. **Nested `Escape`**, all three levels.
9. **Ladder selection** — decade/screen-floor choice, major/minor, the ≥ 3 rung
   floor, the `Ctrl` dim.
10. **Tag leader placement** with the frame flip, reusing `placeProposal`'s
    arithmetic rather than a second copy of it.

### 6.3 The `packages/design` boundary question — decide it now

**`packages/design` has no `three`, no `@react-three/fiber`, no
`@react-three/drei`** (MEASURED: grep for `from "three"` / `@react-three` across
`packages/design/src` returns nothing; the package's only runtime dependency
besides fonts is `@loft/ts-client`). CRAFT-8's roadmap row says the primitive
lands in `packages/design/**`. Taken literally that means adding three heavy
peer dependencies to the design system so it can render meshes — which would
make every `packages/design` unit test boot a WebGL stack, and would put
viewport rendering inside the package the DOM chrome imports.

**Decision: split CRAFT-8 along the seam the repo already uses everywhere else
(`extrudeHandle.ts` ↔ `ExtrudeDragHandle.tsx`, `extrudeGhost.ts` ↔
`ExtrudePreview.tsx`).**

| lands in | contents | dependencies |
|---|---|---|
| **`packages/design/src/primitives/`** | `AxisGrip` (exists), `DimensionTag` (exists), **`GaugeTag`** — the tag + leader + readout⇄input cell as one component, DOM only | none new |
| **`packages/design/src/gauge.ts`** | `GaugeTrack` interface, the three track factories, ladder selection, `steppedValue`, `quantize`, clamps — **pure arithmetic on plain `[x,y,z]` tuples**, no `three` | none new |
| **`packages/design/src/units.ts`** | **`formatAngle`** added beside `formatLength` (§1.9) | none new |
| **`apps/web/src/viewport/ParametricGauge.tsx`** | the r3f shell: meshes, `Html`, the ask-queue, pointer capture, the sleeve | `three`, r3f, drei — where they already live |

**Plain tuples, not `Vector3`, in the pure module.** `three`'s `Vector3` is
mutable and allocating; the arithmetic is ~40 lines either way, and keeping it
tuple-based is what lets `packages/design` stay dependency-clean and unit-tested
in jsdom. The r3f shell converts at the boundary, as `extrudeHandle.ts` already
does in reverse.

A builder who finds this split wrong must say so **before** writing code, in the
review of CRAFT-8 — not by adding `three` to `packages/design/package.json`
halfway through CRAFT-10.

### 6.4 The explicit list of "if you need this later, CRAFT-8 must add it now"

I went through 9/10/11 asking what each would need to reach back for. Four
things, all of which CRAFT-8 must land even though extrude does not use them:

1. **`companion`** — a second cell on one tag. Only hole (depth + Ø) needs it.
   Landing it later means changing the tag's layout after three items have
   shipped against the one-cell version.
2. **`formatAngle`** — only CRAFT-10 needs it, but it is a `units.ts` change and
   `units.ts` is not CRAFT-10's territory.
3. **`tag: "none"`** — pattern mounts two gauges; two tags 20 mm apart carrying
   different numbers is the "two dialects drawn on screen" failure literally. The
   spacing gauge shows a tag; the count gauge shows a **count pip** (`N 6`) in
   the same tag strip. Only CRAFT-11 needs the suppression.
4. **`stops` returning `{major, minor}` rather than a flat array** — only the
   angular track distinguishes them today, but flattening now forces a signature
   change later, which is the `ViewCreate.auto_place` trap this repo has already
   paid for once (a required-field change and its callers in one commit).

**Everything else 9/10/11 need is a new `GaugeTrack`, which is additive by
construction.** If a builder finds a fifth, that is a direction defect — escalate
rather than patching the primitive mid-wave.

---

## 7. DECISION 6 — the contracts split across two builders

W2 had one: the chip binds keys in the capture phase with `preventDefault()`, so
the opener had to start `if (event.defaultPrevented) return;` — miss either half
and `E` opens Extrude on the wrong profile *and looks right doing it*. W3 has
three. **Carry each to BOTH builders in these words, including the broken-state
sentence.**

### 7.1 CONTRACT α — the digit capture is a global key listener

*Between: CRAFT-8 (registers it) and every item that mounts a gauge.*

The digit handoff (§4.1) is a **window** keydown listener. `lib/modalGate.ts`
exists as the general answer to exactly this and carries an audit test that
**fails by name when a new raw global key listener appears**, plus an alarm when
a key reaches the workspace while an `[aria-modal="true"]` element is on screen.
W2 walked straight past `modalGate` because it had been generalised to exactly
one registrant.

- **CRAFT-8 registers the gauge's digit capture through `modalGate`, never as a
  raw `window.addEventListener`.**
- **Every item that mounts a gauge verifies the audit test still passes** and
  does not add a listener of its own.

**Broken state:** the audit test goes red naming the new listener (good), or —
if someone routes around it — a digit typed while a gauge is live and a modal is
open reaches the gauge instead of the modal, which is FLOW-A1's and W2's shared
defect for the third time.

### 7.2 CONTRACT β — the gauge asks, the editor must echo, and PartPage must reset

*Between: whoever mounts the gauge (viewport) and whoever owns the editor
(components) — different files, and for CRAFT-9 different verbs.*

The gauge renders `shown = live ?? value`, where `live` is its own last ask, and
**`endDrag` sets `live = null`**. So:

> **If the editor takes `onChange` but the gauge's `value` prop is not fed from
> the editor's echoed state, the arrow springs back to its starting length the
> instant you let go — while the rail field shows the number you dragged to.**

Both halves look finished on their own. The drag is smooth and correct for its
entire duration; the defect fires on `pointerup`, which is after every
screenshot anyone would take. The mirror is just as quiet:

> **If `closeEditor` does not clear the override, the next open of that command
> seeds from the last drag instead of its default.**

The three anchors, per item:

| anchor | file:line | what goes there |
|---|---|---|
| **A — state** | `PartPage.tsx:1684` | `const [xOverride, setXOverride] = useState<{v:number}|null>(null)` + the `useCallback` setter |
| **B — reset** | `PartPage.tsx:3093` (`closeEditor`) | `setXOverride(null)` — **the line everyone forgets** |
| **C — echo** | `PartPage.tsx:5143-5320` (the editor block) | one `xOverride={xOverride}` prop on your own editor element |
| **D — mount** | `PartPage.tsx:5518-5530` (viewport children) | one `<XGauge …>` |

CRAFT-8 lands a `useGaugeOverride()` hook so A and B are **one call**, used once
by extrude in the same commit. Then each later item adds one hook call, one
prop, one mount — three one-line insertions at three named anchors. That is what
converts a shared 5 808-line file from a deadlock into an ordered queue.

### 7.3 CONTRACT γ — mid-drag Escape must be swallowed before the command sees it

*Between: CRAFT-8 (the gauge) and the global cancel in `PartPage`.*

The global editor cancel (FINDINGS #11) listens for Escape and closes the
editor. The nested rule (§4.3) requires the gauge to take Escape **first** while
`grabbed` is true, revert, release pointer capture, and `stopPropagation`.

**Broken state if the gauge does not swallow it:** the editor unmounts while the
pointer is still captured by a node that no longer exists; the drag has no
terminator; the next `pointerup` goes nowhere and the user is left holding a
button over a canvas that has silently changed mode. It will not throw and it
will not show in a screenshot.

**Broken state if the global cancel is removed instead:** Escape stops cancelling
commands, which is what the band promises in words on screen.

Both halves, same words, both briefs.

---

## 8. DECISION 7 — territory, ordering, and the file nobody owns

### 8.1 The two contended files, and the allocation

MEASURED: `apps/web/src/routes/PartPage.tsx` is **5 808 lines** and is the
integration point for all five items while belonging to none of their subtrees —
the identical shape W2 hit. `packages/design` is the second, because CRAFT-8
lives there and 7/9/10/11 all consume it.

**Allocation, by exact anchor and by order:**

| # | item | owns | touches in `PartPage.tsx` | touches in `packages/design` |
|---|---|---|---|---|
| 1 | **CRAFT-8** ⚑ | `packages/design/src/{gauge.ts,units.ts,primitives/GaugeTag.tsx}` + `apps/web/src/viewport/ParametricGauge.tsx` + `ExtrudeDragHandle.tsx` | **all four anchors A/B/C/D, once, for extrude only** — and lands `useGaugeOverride()` | **everything. It is the only item that may.** |
| 2 | **CRAFT-7** | `apps/web/src/viewport/{ParametricGauge,extrudeHandle}.*` | nothing | nothing |
| 3 | **CRAFT-9** | `apps/web/src/viewport/` gauges + `components/{Fillet,Chamfer,Shell,Hole,Datum}Editor.tsx` | A/B via the hook ×5, C ×5, D ×5 | nothing |
| 4 | **CRAFT-10** | `apps/web/src/viewport/` gauges + `components/{Revolve,Draft}Editor.tsx` | A/B ×2, C ×2, D ×2 | nothing |
| 5 | **CRAFT-11** | `apps/web/src/viewport/` gauges + `components/PatternEditor.tsx` | A/B ×1, C ×1, D ×2 | nothing |

**`packages/design` is CRAFT-8's alone, for the whole wave.** If 9/10/11 need a
primitive change, they **stop and escalate** — that is the foundation item's
contract, and §6.4 exists so it should not happen.

### 8.2 Ordering — and why 9/10/11 are genuinely parallel

```
CRAFT-8  ──►  CRAFT-7  ──┬──►  CRAFT-9   (linear  × 5 verbs)
  (alone)     (alone)    ├──►  CRAFT-10  (angular × 2 verbs)
                         └──►  CRAFT-11  (stepped + linear, pattern)
```

- **CRAFT-8 lands first and alone.** It is a pure refactor plus the seam, and
  the seam is what the other four build against.
- **CRAFT-7 lands second and alone**, because it changes the primitive's drawn
  form and its hit model. Landing it *after* 9/10/11 would mean repairing five
  gauges instead of one. Landing it *inside* CRAFT-8 would break CRAFT-8's
  "must not move a pixel" gate, which is the only cheap way to know the refactor
  was faithful.
- **9, 10 and 11 are then fully parallel** — disjoint editors, disjoint viewport
  components, and disjoint one-line insertions at the four anchors. Their only
  shared file is `PartPage.tsx`, and their hunks are in four known places.
- **Each must stage hunks, not files, for `PartPage.tsx`.** It is not on the
  usual ROADMAP/BACKLOG list but it has every one of that list's properties this
  wave. `git diff --cached`, read in full, before every commit.

### 8.3 CRAFT-9 is too big as written — split it

CRAFT-9 covers **five verbs and five editors** (fillet radius, chamfer distance,
shell thickness, hole depth + Ø, datum offset). CRAFT-10 covers two, CRAFT-11
one. That is not a wave item, it is three.

**PROPOSED split, in value order:**

- **CRAFT-9a** — fillet radius + chamfer distance. Same track, same anchor
  (an edge), same ghost problem; one builder, one shape of solution.
- **CRAFT-9b** — shell thickness + datum offset. Both are offsets from a picked
  face/plane; the track is the face normal.
- **CRAFT-9c** — hole depth + Ø. The only `companion` two-cell gauge; do it last,
  when the tag has settled.

### 8.4 The ghost problem, which is the real cost of 9/10/11

MEASURED (§1.3): none of these verbs has a live preview. **A gauge whose drag
changes a number and not the model is worse than the form it replaces** — it
promises direct manipulation and delivers a slider. So each item must choose,
explicitly, in its commit message:

- **(a) ship a ghost with the gauge** — a translucent preview of the result; or
- **(b) ship a *geometric* preview short of a full ghost** — for fillet, the
  rolling-ball tangent circle drawn on the picked edge at the current radius;
  for chamfer, the bevel band; for shell, the inner offset outline; for revolve,
  the swept arc and its end plane; for pattern, ghost copies at the instance
  positions. **This is the recommended route:** it is line-work, it belongs to
  idiom D, it needs no kernel round-trip, and it answers the only question the
  drag actually poses — *how big is that?*

**(c) "the field updates and the model does not" is not an option.** Any item
that would ship (c) must be deferred to W5 instead. Say which of (a)/(b) you
shipped, in words, in the commit.

---

## 9. The per-item briefs

Each is executable without re-deciding anything above. Acceptance criteria that
differ from `REDESIGN-ROADMAP.md` are marked **AMENDED** with the reason.

### CRAFT-8 ⚑ — extract `<ParametricGauge>` · **first and alone**

**Territory:** `packages/design/src/{gauge.ts, units.ts, primitives/GaugeTag.tsx,
index.ts}` · `apps/web/src/viewport/{ParametricGauge.tsx, ExtrudeDragHandle.tsx,
extrudeHandle.ts}` · `apps/web/src/routes/PartPage.tsx` anchors A/B/C/D ·
`apps/web/src/components/ExtrudeEditor.tsx`.

**Do:**
1. The four-way split in §6.3. Pure arithmetic on tuples in
   `packages/design/src/gauge.ts`; the `linear` track is today's
   `extrudeHandle.ts` arithmetic moved, not rewritten.
2. `GaugeTag` in `packages/design/src/primitives/` — tag + leader + the
   readout⇄input cell, DOM only, reusing `DimensionTag`/`DimensionTagCell`
   (which already has both states) and `ProposalNote`'s leader geometry.
3. `formatAngle` in `units.ts`, beside `formatLength`, with the same
   `unitSuffix` option. Do **not** migrate the three existing call sites —
   that is a separate DRY item and would expand this one's blast radius.
4. `ParametricGauge.tsx` in `viewport/` — the r3f shell, carrying §6.2's ten
   behaviours. Move the ask-queue **verbatim**, comment and all.
5. `useGaugeOverride()` — anchors A and B as one call.
6. Re-express the extrude gauge through it. `ExtrudeDragHandle.tsx` becomes a
   thin call site or disappears into the mount.

**Do NOT:** change the drawn form, the proportions, the ladder, the hit region,
the digit capture, or the Escape nesting. **All of those are CRAFT-7.**

**Proven by (unchanged from the roadmap):** pure refactor — `extrude-drag-handle
.spec.ts` green untouched, `extrudeHandle.test.ts` green, **and a screenshot
match against `docs/design/screenshots/w3-direction/w3-before-extrude-1280.png`
and `-1600.png`.** A refactor must not move a pixel; these are the before halves.

**Mutation proof required:** break one reconciliation rule in the moved
ask-queue (e.g. clear the queue on every `value` change) and show the existing
keyboard case reddens. The queue's correctness is invisible to a normal run —
that is why it was written after a load-dependent bug — so a refactor that
carries it needs a positive control that it is still load-bearing.

---

### CRAFT-7 — fix the extrude grip · **second and alone**

**Territory:** `apps/web/src/viewport/{ParametricGauge.tsx, extrudeHandle.ts}` ·
`packages/design/src/gauge.ts` (ladder selection only).

**Do:**
1. **The hit sleeve.** A drei-`Html` band along the projected track: a rotated
   `div`, `transform: rotate(θ)`, length = projected track length, **height =
   max(12 px, the drawn shaft's projected width)**, transparent,
   `aria-hidden`, `tabIndex={-1}`, sharing the grip's pointer handlers.
   `data-gauge` on both it and the grip.
   *Why DOM and not a raycast mesh:* this repo has already solved this exact
   problem once — the drawing-sheet dimension pick, where a 2.6 mm-stroked SVG
   `<line>` measured `118.1 × 0.0 px` because `getBoundingClientRect` ignores
   stroke, and the fix was **a rotated filled `<rect>` of the same band**
   (9/18 → 14/18 reachable points). A raycast mesh would be invisible to
   `elementFromPoint`, to Playwright's actionability check, to any touch-target
   audit, and to assistive tech — which is how a manipulator rots silently. A
   3 mm-wide shaft projects to ~5 px at the default camera; **5 px is not a
   target.**
   *Constraint:* the sleeve exists **only while its command is open**, so it can
   never occlude a face pick.
2. **Proportion fixes** — §2.2, both clamps, with unit tests across five decades
   rather than a constant asserting itself.
3. **Ladder = snap stops** — §3.1–3.3, including the 14 px screen floor, the
   major/minor draw, the ≥ 3 rung floor, and the `Ctrl` dim.
4. **The tag becomes an input** — drop `readout`, wire `value`/`onChange`.
   `DimensionTagCell` already renders both. Add the leader (§2.1).
5. **Digit capture, `Tab` ⇄ cell, nested `Escape`** — §4, contracts α and γ.
6. **Remove the rest-state collar** (§2.1).
7. **ADDED AFTER CRAFT-8's REVIEW — draw the spine as a polyline, not a chord.**
   `ParametricGauge.tsx`'s `pose` builds ONE `CylinderGeometry` between
   `drawing.spine[0]` and `drawing.spine[len-1]` and discards every intermediate
   point — while `TrackDrawing.spine` is documented as *"two points for a
   straight track, a polyline for an arc"* and `angularTrack.draw` duly emits
   one. Measured: a 90 degree sweep at radius 20 yields a 25-point spine whose
   chord departs from the true arc by **5.86 world units**, 29 % of the radius.
   Render the spine as a chain of segment cylinders (or a `TubeGeometry`); a
   2-point spine reduces to today's single cylinder, so extrude is unaffected.
   This is in CRAFT-7 because CRAFT-7 owns `ParametricGauge.tsx` and CRAFT-10
   does not — as landed, CRAFT-10 could not mount an angular gauge without
   reopening a file outside its territory.
8. **ADDED AFTER CRAFT-8's REVIEW — close the two §6.1 gaps.** `tagSide` is
   absent from `ParametricGaugeProps`, and `companion` shipped narrowed to
   `Pick<GaugeCell, "tagLabel" | "value">`, so the companion cell is formatted
   with the PRIMARY track's formatter. Fine for hole (depth mm + diameter mm),
   wrong for any mixed-unit pair — which is why §6.1 gave the companion its own
   `track`. Add `tagSide`; either restore the full `companion` shape or state in
   §6.1 that companion is display-only and same-unit. Also note the tag leader
   is **not** a one-prop flip as CRAFT-8 reported: `placeGaugeTag` is exported
   and unit-tested but has no shipped call site, and `ParametricGauge` never
   imports it, so wiring it means measuring the tag box, resolving the frame and
   threading `placement` through — inside `ParametricGauge.tsx`, which is yours.

**Proven by — AMENDED:** the roadmap says *"`elementFromPoint` down the gauge
axis resolves to `extrude-depth-handle` at ≥ 8 of 12 offsets (today 3 of 15)"*.
Taken literally that forces the **slider's own box** to swallow the whole axis,
which breaks `extrude-drag-handle.spec.ts`'s `gripCentre()` helper (it drags the
bounding-box centre — which would become the middle of the shaft) and makes the
slider's accessible target a 101 × 12 px band. Amended to:

> `document.elementFromPoint` down the projected track resolves to an element
> with a `[data-gauge="extrude-depth"]` ancestor at **≥ 12 of 16** offsets
> (measured today: **2 of 16**), **and** a real `page.mouse.down/move/up`
> starting at the track's midpoint changes `extrude-distance` (measured today:
> it does not — the field stayed at 40).

12 of 16 rather than 8 of 12 because the two endpoints legitimately fall outside
(t=0 is on the sketch plane, t=1 is past the arrow's point). The second clause is
the one that matters: it asserts with the user's own mechanism, not a proxy.
**Do not add `force: true` anywhere.** This repo has measured that flag hiding a
zero-area target; it is evidence of a defect, not a workaround for one.

---

### CRAFT-9a/b/c — linear gauges · **parallel with 10 and 11**

**9a fillet radius + chamfer distance** · **9b shell thickness + datum offset** ·
**9c hole depth + Ø** (the only `companion` gauge).

**Track:** `linear`. **Anchor:** 9a on the picked edge's midpoint, normal to the
edge, in the face-pair's bisector plane; 9b on the picked face's centroid along
its normal; 9c on the hole axis.

**Each must:** state which of §8.4's (a)/(b) it shipped and show it. The
recommended line-work previews: 9a the rolling-ball tangent circle at the
current radius on the picked edge; 9b the inner offset outline; 9c the bore
circle and the depth plane.

**Proven by, per verb:** drag N px → the editor field changes **and** the preview
redraws; arrow keys step the same value; `elementFromPoint` reaches the track at
≥ 12 of 16 offsets; the round-trip contract β check — **release the pointer and
the instrument stays where you dragged it** (this is the one that catches a
missing echo).

---

### CRAFT-10 — angular gauges · **parallel**

Revolve angle, draft angle, bend angle. **Track:** `angular`, with the 15°/5°
ladder (§3.4) and `formatAngle`.

**Prerequisite this item owns:** MEASURED — **the revolve axis is not drawn in
the viewport at all.** It is chosen from a dropdown reading *"Y axis · through
the origin"* and the scene shows nothing
(`w3-before-revolve-1280.png`). An arc gauge with no visible axis is an arc
around nothing. **Draw the axis first**, as a brass centreline in idiom D's
vocabulary, then hang the arc on it. That is not scope creep; it is the arc's
anchor.

**Do not** derive the angular ladder from the linear one. 10/20/50° is the
failure mode; 15/5° is the decision.

---

### CRAFT-11 — pattern gauges · **parallel**

**Two mounts** (§5.3): a `stepped` count gauge along the pattern direction and a
`linear` spacing gauge across the first gap. Ghost copies at the instance
positions are the preview — route (b), and for this verb they are also the
`stepped` track's stops, so the preview and the ladder are the same drawing.

**`tag: "none"` on one of them.** Two tags 20 mm apart carrying different numbers
is the "two dialects on screen" failure drawn literally.

**Proven by — AMENDED from one criterion to two, per §5.3:** dragging the
spacing gauge changes `pattern-spacing` and does **not** change `pattern-count`;
dragging the count gauge past a rung increments `pattern-count` and does **not**
change `pattern-spacing`. The roadmap's single criterion conflated them.

---

## 10. What the flow-cost metric will say about this wave, stated before the wave runs

**It will not move, and any claim that it did is a lie.** Stated now so nobody
has to argue about it later.

`scripts/check-flow-cost.py --journey fillet` reports the full fillet authoring
journey in `fillet-chamfer.spec.ts` at **3 gestures** (API-seeded, tagged
`partial`): click `new-fillet`, fill the radius, click Create. A gauge version is
**also 3**: click `new-fillet`, drag, Enter. The canonical
register→part→sketch→extrude→edit→export journey reads **30** and will still
read 30, for the reason the roadmap already records about W2 — nothing makes the
new path the path `full-flow.spec.ts` takes.

The metric models an expert who already knows every verb, and **it is
structurally blind to the thing this wave is for**: it counts the gestures, not
the fact that the engineer does not know what 5 mm of fillet looks like on this
part until they have typed it, submitted it, waited for the kernel, looked, and
typed a different number. That loop costs 3 gestures and forty seconds; the drag
costs 3 gestures and two seconds, and the difference is the entire product.

**So W3's evidence is screenshots, per-verb reach counts, and the release test
from contract β — not the gesture number.** Filed as a known blind spot, not as
a reason to distrust the metric: it was right about W2 and it is honest here too.

---

## 11. What I deliberately did NOT decide, and why

1. **Whether the rail editor panel survives.** CRAFT-15/16 (W5) propose moving
   editors onto the geometry. If that lands, the gauge's tag and the panel's
   field merge. I am deliberately **not** pre-empting it: W3's job is to make the
   number pullable, and a gauge that writes the existing field composes with
   either outcome. Do not delete the rail field in W3.
2. **Persistent selection (CRAFT-12, W4).** 9a/9b/9c need an anchor — a picked
   edge or face — and today that comes from each editor's own pick state. When
   CRAFT-12 lands a selection store, those anchors should read from it. **W3
   gauges must take their anchor as a prop**, never reach into a pick store, so
   W4 is a re-wiring and not a rewrite. That is a constraint, not a decision
   about W4.
3. **Multi-value direct manipulation beyond `companion`'s two cells.** Sweep,
   loft and the sheet-metal verbs have parameter sets a single track cannot
   express. Out of scope; do not stretch the primitive to reach them.
4. **Touch.** The 24 px grip meets WCAG 2.2 SC 2.5.8 and the sleeve will be ≥ 12
   px, but I did not test on a tablet-class viewport this pass — my two probes
   were mouse-driven at 1280×800 and 1600×1000. **A touch pass on the shipped
   gauge is a W3-exit QA item**, not a design decision, and I am flagging rather
   than guessing.
5. **Migrating the three angle formatters** onto the new `formatAngle` (§1.9).
   CRAFT-8 adds it; converging `measure/geometry.ts`, `features/revolve.ts` and
   `features/hole.ts` touches three territories and belongs in its own item.
   Filed for the groomer as a DRY row; I did not write it to the board, which is
   the groomer's file.
6. **The stale `CLAUDE.md` sentence** (§1.1). Editing `CLAUDE.md` is not my
   territory. **Orchestrator action:** the mandate's *"a form with no handle at
   all"* should read *"a handle you cannot reach: the extrude gauge ships, and
   2 of 16 points along its own drawn axis are hittable"*. Three briefs have now
   quoted the stale version as fact.
7. **Whether the ladder-as-snap-stops decision (§3.1) should also change the
   IMPERIAL step.** `SNAP_MM.in = 25.4/32` is a named, human step and a decade
   ladder would replace it with something nobody says out loud. My instinct is
   that the imperial ladder should be a **binary** series (1/32, 1/16, 1/8, 1/4,
   1/2, 1 in) with the same screen floor — but I did not measure an inch document
   this pass and will not decide it from the armchair. **CRAFT-7 must measure it
   on a real inch part and say what it chose.**

---

## Appendix — evidence index

| file | what it shows |
|---|---|
| `w3-before-extrude-1280.png` / `-1600.png` | the extrude gauge open, 40 mm — **CRAFT-8's pixel-match baseline** |
| `w3-before-gauge-rest-1280.png` | the instrument at rest: unattached tag, head-heavy arrow, no visible grip |
| `w3-before-gauge-hover-1280.png` | hover: the ladder as crosshatch over the arrowhead (§1.5) |
| `w3-before-fillet-1280.png` | radius 2 in the rail; the cube unrounded, unhighlighted, unannotated |
| `w3-before-revolve-1280.png` | the revolve axis chosen in a dropdown and drawn nowhere |
| `w3-before-pattern-1280.png` | count 3 / spacing 10 / +X, no copies previewed |
| `w3-before-chamfer-1280.png`, `-shell-`, `-hole-` | the same story for the remaining verbs |

**How to reproduce:** native stack per `CLAUDE.md` (uvicorn + SQLite
`metadata.create_all`) on :8100/:8101/:8102, Vite :5311 via an isolated
Playwright config, real Chromium. The two probe specs were temporary, formatted
on creation and deleted in the same pass — they are measurement instruments, not
gates. The measurements a builder should re-take before starting are the axis
sweep (§1.2) and the per-verb handle sweep (§1.3); both are ten lines.

---

## 12. RECONCILIATION — written after CRAFT-8 landed and was reviewed

Three things in this document were wrong, ambiguous, or have been overtaken by
what shipped. They are corrected here rather than edited away, because the
reasoning that produced them is still worth reading.

### 12.1 The track factories: §6.3 and §8.1 win; §6.4's "additive" sentence is the odd one out

§6.3's table says `gauge.ts` holds **the three track factories**. §8.1 says
9/10/11 touch `packages/design`: **nothing**, and that the package is CRAFT-8's
alone for the whole wave, with "stop and escalate" if they need a change.
§6.4's closing reasoning — that a new `GaugeTrack` is *"additive by
construction"* and therefore need not land now — cannot hold beside those two:
a later item that needs a factory would have to either add one (forbidden by
§8.1) or escalate (which is the deadlock §8 exists to prevent).

**So the shipped reading is the correct one: all three factories landed in
CRAFT-8.** `linearTrack` has a shipped call site; `steppedTrack` and
`angularTrack` do not, and their unit tests are their only witness — which the
test file says out loud in its own `describe` name.

**But `angularTrack`'s signature is hereby PROVISIONAL.** It was designed
against no caller, and CRAFT-8's review has already found one place where the
shell cannot honour what it emits (the chord defect, now CRAFT-7 item 7). When
CRAFT-10 mounts the first real angular gauge, **changing `angularTrack` does not
count as reopening a closed package** and does not require an escalation — it is
the first use finding out what the interface should have been. `steppedTrack`
gets the same licence for CRAFT-11.

This is the repo's own DRY rule showing its teeth: *extract on the second real
use, not the first imagined one.* We extracted on the first imagined use because
the territory rule made the alternative worse. That is a defensible trade and it
is not free — this clause is the price.

### 12.2 The screenshot noise floor is not a gate; do not reuse it as one

CRAFT-8 proved "it must not move a pixel" against a floor built from **one**
same-code pair. Its review re-measured with six captures and all fifteen
pairwise comparisons, at CRAFT-8's own `d >= 24` metric:

```
NOISE FLOOR (d>=24), 15 pairs:  min=87   median=266   max=23077
CRAFT-8's reading:              1280: 86 against a floor of 110
                                1600: 28 against a floor of 287
```

Three consequences, and the first is the one that matters.

- **The distribution is bimodal, and the high mode recurs at roughly 1 in 6.**
  One of six identical-code captures differed across the full frame width. That
  is the same shape CRAFT-8 saw once and dismissed after a repeat — a coherent
  124 px column — and it is not antialiasing, it is structural. So this
  procedure can report a regression that does not exist, which it nearly did.
- **86 against 110 is not clearance.** 86 sits at the minimum of the same
  distribution (min 87) whose median is 266. Two draws from the low mode of a
  bimodal process, ordered, are not a floor and a signal. The honest sentence is
  *"at 1280 the difference is indistinguishable from run-to-run noise"*. Only
  the 1600 reading (28 against 287, a 10x margin) carries weight.
- **The `d >= 24` residual is not on the grid.** In every low-mode pair it sits
  in a ~193x133 box on the gauge and its ghost — i.e. the metric's noise lives
  exactly where a real change would live.

**For CRAFT-7 / 9 / 10 / 11, the "did not move a pixel" gate is the
DETERMINISTIC DOM PROBE**, not a screenshot diff: the grip's bounding box, the
`aria-value*` triple and `data-step`/`data-coarse-step` read at three fixed
values. Its own repeatability is measurable (~0.09 px here) and it costs a
fraction of a capture. If a pixel comparison is genuinely wanted, it needs at
least five noise pairs and a max-or-high-quantile floor.

Corollary worth carrying beyond this wave: **a single-sample "control" is not a
control.** It cannot estimate dispersion, so it cannot tell you whether the
number beside it means anything.

### 12.3 The committed `w3-before-extrude-*.png` baselines cannot serve as a baseline

They were captured PERSP with the grid off, by a probe spec that was deleted in
the same pass. Nothing reproducible renders that state now, so a diff against
them measures the procedure rather than the change. They remain useful as
*illustrations* of the before state for the founder; they are not evidence.
The other eight frames in that directory are unaffected — they are per-verb
"this verb has no handle at all" evidence, which does not depend on camera
state.
