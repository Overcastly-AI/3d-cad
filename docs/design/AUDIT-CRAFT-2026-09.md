# CRAFT AUDIT — 2026-09-11

**Brief (founder, verbatim):** *"changes are encouraged to feel more like Fusion
360 or Plasticity."*

**Lens.** Craft only: how the thing looks, how it responds under the hand, and
whether it reads as a precision instrument or as a web app with a 3D view in
it. Not feature coverage, not the part-creation journey (an independent auditor
is on that in the same window; we did not coordinate, by design).

**Skill.** `.claude/skills/frontend-design/SKILL.md` was read before any
aesthetic judgement was formed. Its calibration list (the three AI-default
looks), its "spend boldness in one place" rule, and its "structure is
information" test are the standards applied in §4.

**Method.** Native stack, no containers — geometry :8072, documents :8071,
gateway :8070 on per-agent SQLite (`craftaudit-*.db`), Vite :5270. Real
Chromium (SwiftShader, DSF 1) at **1280×800** and **1920×1200**. Parts built
through the real gateway: an 80×60×12 plate, a four-bore bolt circle, and a
fillet — plus a deliberately failing fillet, which turned out to be one of the
most useful frames in the pass.

**Tree under test: `f00fbe9`** (tip of `claude/branch-review-development-hkbbnb`),
NOT `main` (`d4552e3`). `main` is 11 commits behind and four of those 11 are
viewport/editor-chrome fixes squarely inside this audit's lens, so auditing
`main` would have produced stale findings. Worktree at `/home/user/craftaudit-wt`.

**Reference honesty.** No Fusion 360 or Plasticity reference image was
available in this container (no image assets in-repo, no fetch path). **No
side-by-side comparison was performed and none is claimed.** Where this audit
invokes those tools it does so against a *written*, specific description of
what they do in the same frame, stated inline so the reader can check the
premise. Every claim about *our* pixels is measured.

**Status of the previous full audit (2026-08-17).** Re-verified, not restated:

| 08-17 finding | status today | evidence |
|---|---|---|
| P1-1 export buried in the inspector | **FIXED** — `EXPORT` is now its own tool group in the top band (`part-export-band-{step,stl,3mf,glb}`) | `02-hero-1280.png` |
| P1-4 ViewCube absent ≤ 800 px viewport height | **FIXED** — cube present at 1280×800 | `07-sharp-body-edges.png` (cube at ≈1140,610) |
| P1-2 register row verbs 27 % of table width | **FIXED** — collapsed to one `part-actions` overflow mark (REGISTER-1) | `support.ts:openRowActions` |
| P1-1 *residue* | **NEW, open** — the inspector's four export cells were not removed when the band gained them; the verb now exists at two addresses (see P3-1) | `02-hero-1280.png` |

**Evidence frames.** All under `docs/design/screenshots/craft-2026-09/`;
referenced below by bare filename.

| file | what it shows |
|---|---|
| `01-hero-1920.png` | the part workspace at 1920 x 1200 |
| `02-hero-1280.png` | the same at 1280 x 800 |
| `03-front-ortho-void.png` | **the frame that fails hardest** - front ortho |
| `04-front-persp-grid.png` | same camera, perspective - the control |
| `05-top-ortho.png` | top ortho |
| `06-filleted-body-no-edges.png` | a filleted plate: zero line work |
| `07-sharp-body-edges.png` | the same plate unfilleted: edges drawn |
| `08-extrude-gauge.png` | the extrude gauge (what already works) |
| `09-extrude-gauge-dragged.png` | after a 64 px drag, 10 -> 21 mm |
| `10-rebuild-failure-state.png` | a kernel refusal, reported honestly |
| `11-sketch-dimension-at-creation.png` | W/H typed where the shape forms |
| `12-plane-pick-mode.png` | modal tool band; no view nav |
| `13-face-hover-and-offer.png` | face hover + the SKETCH proposal chip |
| `14-click-selects-nothing.png` | after clicking that face and moving away |
| `15-sketch-vertex-drag-noop.png` | a corner drag that did nothing |
| `16-viewcube-no-refit.png` | a ViewCube facet click leaves the body off-frame |

---

## 1. THE DIRECT-MANIPULATION TABLE

The mandate's plainest sentence: *"Fusion's extrude is a draggable arrow; the
numeric field is the precision fallback. Ours is a form with no handle at all."*

**That sentence is now 1/40th wrong and 39/40ths right.** The extrude gauge
shipped and it is good (§5, "what already works"). Nothing else did.

### 1a. The exhaustive census of grabbable things

Measured, not inferred — a repo-wide scan for every manipulator affordance:

```
$ grep -rno 'data-testid="[^"]*(grip|handle|gizmo|drag|arrow|manip)[^"]*"' apps/web/src packages/design/src
apps/web/src/viewport/ExtrudeDragHandle.tsx : extrude-depth-handle
apps/web/src/components/DrawingSheet.tsx    : drawing-view-drag
apps/web/src/components/DrawingSheet.tsx    : drawing-view-grip
```
plus `feature-grip-N` (tree reorder) and `timeline-stop` (`role="slider"`).
**Five grabbable objects in the whole product, one of which is in the 3D scene.**

### 1b. Every parametric value a user can set

`H` = viewport handle · `Hv` = hover affordance on the value · `K` = keyboard
path other than tabbing to the form · `Form` = the form is the only route.

| # | Value | Surface | H | Hv | K | Route today |
|---|---|---|---|---|---|---|
| 1 | **Extrude distance** | `ExtrudeEditor` / `ExtrudeDragHandle` | ✅ brass gauge + graduated ladder | ✅ grip | ✅ arrows ½ step, Shift/Page ×10, announced | **handle + form** |
| 2 | Extrude direction (normal / reverse) | `ExtrudeEditor` | ❌ | ❌ | ❌ | form (segmented control) |
| 3 | Extrude operation (add / cut) | `ExtrudeEditor` | ❌ | ❌ | ❌ | form |
| 4 | Revolve angle | `RevolveEditor` | ❌ | ❌ | ❌ | form only |
| 5 | Revolve axis | `RevolveEditor` | ❌ | ❌ | ❌ | form (select) |
| 6 | **Fillet radius** | `FilletEditor` | ❌ | ❌ | ❌ | form only |
| 7 | **Chamfer distance** | `ChamferEditor` | ❌ | ❌ | ❌ | form only |
| 8 | Shell thickness | `ShellEditor` | ❌ | ❌ | ❌ | form only |
| 9 | Draft angle | `DraftEditor` | ❌ | ❌ | ❌ | form only |
| 10 | Draft neutral offset | `DraftEditor` | ❌ | ❌ | ❌ | form only |
| 11 | Hole diameter | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 12 | Hole depth / blind depth | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 13 | Hole position X | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 14 | Hole position Y | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 15 | C'bore Ø | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 16 | C'bore depth | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 17 | C'sink Ø | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 18 | C'sink included angle | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 19 | Thread pitch | `HoleEditor` | ❌ | ❌ | ❌ | form only |
| 20 | Pattern count | `PatternEditor` | ❌ | ❌ | ❌ | form only |
| 21 | **Pattern spacing** | `PatternEditor` | ❌ | ❌ | ❌ | form only |
| 22 | Pattern angle | `PatternEditor` | ❌ | ❌ | ❌ | form only |
| 23 | Pattern axis X / Y / Z | `PatternEditor` | ❌ | ❌ | ❌ | form only (3 fields) |
| 24 | **Datum plane offset** | `DatumEditor` | ❌ | ❌ | ❌ | form only |
| 25 | Sketch-plane offset | `SketchStrip` | ❌ | ❌ | ❌ | form only |
| 26 | Base-flange gauge | `BaseFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 27 | Base-flange bend radius | `BaseFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 28 | Base-flange K-factor | `BaseFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 29 | **Edge-flange length** | `EdgeFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 30 | Edge-flange width | `EdgeFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 31 | Edge-flange bend angle | `EdgeFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 32 | Edge-flange bend radius | `EdgeFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 33 | Edge-flange offset from edge start | `EdgeFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 34 | Edge-flange K-factor | `EdgeFlangeEditor` | ❌ | ❌ | ❌ | form only |
| 35 | Hem return length | `HemEditor` | ❌ | ❌ | ❌ | form only |
| 36 | Hem bend radius / K-factor | `HemEditor` | ❌ | ❌ | ❌ | form only (2) |
| 37 | Corner-relief notch size | `CornerReliefEditor` | ❌ | ❌ | ❌ | form only |
| 38 | Corner-relief ratio | `CornerReliefEditor` | ❌ | ❌ | ❌ | form only |
| — | **SKETCH** | | | | | |
| 39 | Rectangle W / H at creation | `SketchScene` + `draw-dimension-*` | drag draws it | ✅ | ✅ type, Tab, Enter | **drag + type-in-place** (FB-16, good) |
| 40 | Line / circle at creation | `SketchScene` | drag draws it | ✅ | ✅ | drag + type |
| 41 | **Existing sketch vertex / endpoint** | `SketchScene` | ❌ **dead gesture** | ❌ | ❌ | **cannot be moved at all** |
| 42 | **Existing sketch line / circle** | `SketchScene` | ❌ | ❌ | ❌ | **cannot be moved at all** |
| 43 | Existing sketch dimension value | `DimensionForm` | ❌ | — | ❌ | form only |
| 44 | Arc / spline control points | `SketchScene` | ❌ after creation | ❌ | ❌ | delete and redraw |
| — | **VIEW / DOCUMENT** | | | | | |
| 45 | Camera orbit / pan / zoom | `Viewport` | ✅ drag / right-drag / wheel | ✅ nav cue | ✅ Home,0,1,2,3,4 | **full** |
| 46 | Camera orientation (named) | `ViewCube`, `ViewBar` | ✅ cube facets steer | ✅ facet hover | ✅ digits | **full** |
| 47 | Feature order | `FeatureTreePanel` | ✅ `feature-grip-N` drag | ✅ | ✅ arrows | **full** |
| 48 | Timeline rollback point | `TimelineStrip` | ✅ `timeline-stop` slider | ✅ `cursor-ew-resize` | ✅ | **full** |
| — | **DRAWINGS / ASSEMBLY** | | | | | |
| 49 | Drawing view placement | `DrawingSheet` | ✅ `drawing-view-grip` | ✅ `cursor: grab` | ✅ arrows nudge | **full** |
| 50 | Drawing dimension placement | `DrawingSheet` | ✅ ghost offset drag | ✅ | ✅ | **full** |
| 51 | Assembly instance placement | `AssemblyScene` | ❌ | ❌ | ❌ | mates only, no free drag |

**Score: 38 of 44 model-authoring parameters (86 %) are reachable only by
typing into a panel on the far left of the screen.** The 6 that are not are
extrude depth and the five sketch-creation gestures. Everything that is *not*
geometry — camera, tree order, timeline, drawing layout — is fully
direct-manipulable, which is the tell: the team knows how to build handles, and
has spent them everywhere except on the numbers the model is made of.

### 1c. Three specific craft defects inside the one handle that DOES exist

Measured on `08-extrude-gauge.png` / `09-extrude-gauge-dragged.png`.

- **The visual affordance is ~10× the hit target.** The drawn gauge (shaft +
  arrowhead + ladder) occupies roughly 60 × 110 px. `elementFromPoint` walked
  down the axis from the grip centre in 10 px steps: the gauge answers at
  offsets **−10, 0, +10** and returns the bare `canvas` at **+20 through
  +120**. So pressing the arrow *body* — the part a Fusion user aims at —
  orbits the camera. The grip is a 24 × 24 disc at the arrow's point, which is
  the AA minimum, not a modelling grab target.
- **The value hanging on the gauge is not typeable.** `ExtrudeDragHandle.tsx:593`
  renders `<DimensionTagCell label="D" readout={…} />`. `readout` is the
  *pointer-inert* mode of a primitive **whose other mode is a real input** and
  which the sketcher already uses that way. So the eye is on the arrow at
  (665, 296) and the keyboard has to travel to a field at (106, 179).
- **One arrow, one direction.** There is no second grip for a symmetric or
  two-sided extrude, and no grip at all for the CUT depth; direction is a
  segmented control in the form.

---

## 2. CHROME INVENTORY — what each element does, and what a click gets you

Enumerated live at 1280 × 800 on a solved 4-feature part: every `button`, `a`,
`input`, `select`, `[role]` and `[tabindex]` with a non-zero box. **80
interactive elements.** Every single one has an accessible name; every gated one
carries its *reason* in that name. Full dump in the pass log; grouped verdict:

| Zone | n | What it does | Decoration? |
|---|---|---|---|
| **Topbar** | 4 | `home-link`, `breadcrumb-register`, `document-unit-select` (live — changes every readout's unit), `sign-out` | none |
| **Tool band** | 28 | 7 CREATE + 9 MODIFY + 7 SHEET METAL + MEASURE + 4 EXPORT. All wired. 7 are `aria-disabled` and every one states why in its own accessible name — e.g. *"Hem — add a base flange first"*, *"Combine — needs two or more bodies"*, *"Import STEP — only the first body can be imported…"* | none |
| **Feature tree / panels** | 21 | per-feature select + suppress, sketch visibility, 6 ORIGIN toggles, body visibility + select, panel collapse | none |
| **Inspector** | 7 | material select (live), 4 export cells, collapse, scroll region | **4 redundant** (see P3-1) |
| **Viewport overlay** | 1 | `nav-cue-dismiss` | none |
| **View bar** | 7 | home / fit / front / top / right / iso / projection. **All verified to steer the camera** (frame hash changes on every one) | none |
| **ViewCube** | 1 canvas | 108 × 108 at (1130, 602). **Verified: a facet click re-orients the camera** | none |
| **Timeline** | 12 | 5 feature chips + 5 rollback slots + `timeline-stop` slider + `to-tip` | none |

**Verdict on mandate 3a(c): the product PASSES the "wire it or delete it" test.**
This is genuinely unusual and worth saying plainly — there is no dead tile, no
fake sparkline, no "Status: OK" that is a constant. Even the PROPERTIES panel
suppresses the Mass row until a material exists rather than printing a zero.

The two failures are the *other* face of the rule — functional things that read
as decoration, or that are functional and unreachable:

- **`timeline-stop` and `rollback-slot-4` occupy the identical 24 × 47 box at
  (700, 753).** Two controls, one pixel footprint, different roles (`slider` vs
  `button`) and contradictory names ("Travel stop" vs "Roll forward to the
  tip"). A pointer cannot choose between them.
- **The `view-projection` toggle names its state, not its action.**
  `aria-label="Projection: perspective"`. A screen-reader user is told what is,
  not what pressing does.
- **MODIFY and SHEET METAL stay icon-only at 1920 px** while CREATE gains text
  labels (`01-hero-1920.png`: `IMPORT SKETCH DATUM EXTRUDE REVOLVE SWEEP LOFT`
  vs sixteen unlabelled glyphs). The labelled group is the one whose verbs
  everyone already knows; the unlabelled one is fillet / chamfer / pattern /
  shell / draft / hole / mirror / combine — exactly the icons a new user cannot
  name. The rule is inverted, and there is 279 px of unused band at 1920.
- **The STATUS readout ("Up to date" / the rebuild verdict) is below the fold at
  1280 × 800.** Present at 1920 (`01-hero-1920.png`), scrolled out of the
  inspector at 1280 (`02-hero-1280.png` — TOPOLOGY's *Edges* row is cut through
  the middle). The one readout that tells you the model on screen is the model
  you asked for is the one the laptop frame hides.

---

## 3. THE VIEWPORT AS HERO — measured against rule 3a

Every number below is from a real frame; the canvas region sampled is
x 336–944, y 104–640 (clear of every DOM panel and overlay).

| 3a test | verdict | measurement |
|---|---|---|
| Grid reads to the horizon (iso/home) | **PASS** | grid ink present in the top-most 50 px band (2 503 px above lum 32) and continuously to the frame edge; a real horizon line with skylight above it — `07-sharp-body-edges.png`, and the crop in the pass log |
| Background has atmosphere | **PASS** | vertical gradient measured top (17, 24, 30) → bottom (11, 15, 19) with a vignette; DOM-painted behind a transparent canvas, from `viewport.atmosphere` tokens |
| Studio shading, never debug-gray | **PARTIAL** | a real procedural 4-stop matcap ("machined aluminium under shop lights"); reads as metal at iso. But see P1-2 — no B-rep edges, no ambient occlusion, no contact shadow |
| Persistent view navigation | **PARTIAL** | ViewCube 108 × 108 present at 1280 × 800 (the 08-17 regression is fixed) and steers; ViewBar home/fit/front/top/right/iso/projection all steer. **Both vanish in sketch mode and plane-pick mode** (`12-plane-pick-mode.png`) |
| Canvas gets the full frame | **PASS** | canvas 1280 × 652 at (0, 100) — full width, panels float over it. 1920: 1920 × 1052 = 88 % of the frame |
| Judged side-by-side vs Fusion/Plasticity | **NOT PERFORMED** — no reference available in this container; see the header |

### The frame that fails hardest

`03-front-ortho-void.png` — **the FRONT orthographic view is a grey rectangle on
an empty field.** Nothing else is on screen. No grid, no horizon, no origin
axes, no body edges, no scale reference. Brightened ×5, the region below the
plate contains a smooth background ramp and *nothing else*.

The decisive measurement, same camera direction, projection the only variable:

| view | grid px ≥ 32 in the clear canvas region |
|---|---|
| front, **perspective** | 7 514 |
| front, **orthographic** | 2 396 — and localised to y 277–445, i.e. the plate's own antialiased silhouette, not grid |
| iso, orthographic | 11 795 |
| top, orthographic | 1 959, max lum 85 — three major lines, invisible at normal gain (`05-top-ortho.png`) |

So it is not "ortho kills the grid" (iso-ortho is fine); it is **axis-aligned
ortho** that does. A plausible mechanism, for a builder to confirm rather than
take from me: `AdaptiveGrid` scales drei's `fadeDistance` by the *orbit radius*
(`AdaptiveGrid.tsx:80`), and drei's grid shader fades on world-distance-to-
camera — an orthographic camera's position is pushed far back for the same
framing, so the whole sheet sits beyond the fade. This is the exact condition
rule 3a(a) forbids, arriving in the three views an engineer uses to check a
part.

---

## 4. THE SIGNATURE ELEMENT AND THE SYSTEM

### Is `packages/design` the single source of truth? — almost entirely YES.

This is the strongest thing in the audit and it should be said before the
criticism. Repo-wide scan of `apps/web/src` for six-digit hex literals,
excluding tests and fixtures: **7 hits, of which 4 are inside comments quoting
a token value and 3 are `#000000`/`#FFFFFF` ramp stops in a procedural mask
generator** (`viewport/bluingWash.ts`). There is **not one duplicated colour
between the DOM and the WebGL scene.** The r3f viewport reads
`@loft/design/tokens` — `viewport.matcap`, `viewport.atmosphere`,
`viewport.modelEdge`, `viewport.facePick`, `viewport.gizmo` — exactly as the
mandate's "one palette, two renderers" requires. Most codebases that claim this
do not survive the grep. This one does.

### The one real system drift: **letter-spacing is not tokenised.**

```
$ grep -o 'tracking-\[[^]]*\]' apps/web/src/**/*.tsx | sort | uniq -c
  79 tracking-[0.14em]
  52 tracking-[0.18em]
  25 tracking-[0.16em]
  10 tracking-[0.2em]
   6 tracking-[0.12em]
   3 tracking-[0.08em]
   2 tracking-[0.32em]
   1 tracking-[0.24em]
   1 tracking-[0.06em]
```
**179 arbitrary-value tracking classes across nine distinct values**, and
`tailwind-preset.ts` has no `letterSpacing` key and `tokens.ts` has no tracking
scale. Tracking is not incidental here — the wide-tracked uppercase eyebrow IS
this UI's voice, on every panel header, every tool group, the wordmark and the
timeline. It is the single most identity-bearing typographic decision in the
product and it exists as 179 magic numbers in screen code. Nine values is also
more than a scale needs; three or four would carry the whole language.
(Same shape, smaller: ~20 arbitrary `w-[Nrem]` field-column widths.)

### The signature element

Per the skill: *spend your boldness in one place, keep everything around it
quiet.* This product has **three** candidate signatures and has not chosen:

1. **The drafting register / scribe line** — the parts list as a ruled log book
   you scribe the next numbered line into. Genuinely nothing a template would
   produce.
2. **The graduated depth gauge** — the extrude arrow's 1/2/5-decade ladder
   (`ExtrudeDragHandle.tsx`). A machinist's depth gauge, not a generic gizmo.
   This is the best of the three and it is visible for about four seconds per
   extrude.
3. **The title-block chrome language** — hairline-ruled cells, terse caps
   eyebrows, a unit stated once per strip, data face with tabular numerals.

They share a coherent world (the drawing office), so this is not incoherence —
but the boldness is spread across three places at one-third strength each, and
the one a user sees for the longest (3) is the quietest. Against the skill's
calibration list, the UI does **not** land on any of the three AI-default looks
— it is not cream/serif/terracotta, not black-with-one-acid-accent (the brass
is warm and used as *state*, not as decoration), and not broadsheet
(border-radius and rules are used sparingly and meaningfully). **The chrome is
distinctive.** The viewport is where it goes generic, and that is the inversion
worth naming: in a CAD tool the scene should be the most characteristic surface
and here it is the least.

### Where it reads templated anyway

The one surface that does trip the skill's calibration list is the **feature
editor card**: label-over-field stacked rows, a segmented control, a checkbox
with a sentence beside it, CANCEL | CREATE at the bottom. Seventeen of them,
identical. That is the generic web form, sitting inside an otherwise distinctive
UI, and it is where the user spends most of their authoring time. See the
redesign proposal in P1-1.

---

## 5. WHAT ALREADY WORKS — do not rebuild these

Proposing to rebuild something already good is worse than proposing nothing.
Five things here are at or near the bar and should be protected:

1. **The extrude command frame** (`08-extrude-gauge.png`). Brass gauge standing
   on the profile, live depth in a drafting tag beside it, translucent brass
   ghost of the result, a command band reading `IN COMMAND ▸ Extrude · CANCEL
   ESC · OK ENTER`. Dragged 64 px → distance 10 → 21 mm, field and gauge one
   value. This is the Fusion read. Extend it; do not touch it.
2. **Dimension typed at creation** (`11-sketch-dimension-at-creation.png`).
   Drop a rectangle and a `W 34 | H 23 | mm` tag appears at the corner with
   *"Type a size · Tab switches · Enter applies"*, with auto-applied C/H/V
   constraint glyphs annotated on the geometry. This is FB-16 done properly and
   it is better than Fusion's equivalent.
3. **The rebuild-failure state** (`10-rebuild-failure-state.png`). A fillet that
   the kernel refused produced: a `PARTIAL BODY` alert naming the excluded
   feature and offering `SHOW EDGE BREAK`; an `ERR` tree row with
   `FILLET_FAILED` and a plain-language cause ("the radius (2.0 mm) may be too
   large for an adjacent face"); `SOLVE: Failed`; `EXPORT: Partial` with a
   warning that the file will be named partial. **Never a silent wrong model.**
   This is the single most trustworthy surface in the product.
4. **Modal, contextual tool bands** (`12-plane-pick-mode.png`). Entering a
   sketch swaps the whole band to `SKETCH / HISTORY / DRAW / MODIFY / CONSTRAIN
   / FINISH` and the breadcrumb to `PICK A PLANE`, then `SKETCH`, with a live
   mode line: `On XY · nothing selected · 8 applied`. Mode is always legible.
5. **The accessibility floor and the gate-reason system.** 80/80 interactive
   elements named; every disabled control states its reason in its own
   accessible name (mouse AND keyboard reachable — no `pointer-events-none`
   tooltip trap); focus ring measured `rgb(227,166,75) solid 2px` at
   `outline-offset: -2px` on every control sampled; root never scrolls at 1280
   × 800 or 1920 × 1200; `prefers-reduced-motion: reduce` honoured
   (`motion-safe:` prefixes throughout, verified matching in-browser).

---

## 6. FINDINGS

### P0-1 — Model authoring — 86 % of parametric values are reachable only by typing into a form on the far left of the screen

*Evidence:* the table in §1b; `08-extrude-gauge.png` (the one exception).
*Subtree:* `apps/web/src/viewport/**` (+ `packages/design/src/primitives/AxisGrip.tsx`).

38 of 44 model-authoring parameters are form-only. There is exactly **one**
manipulator in the 3D scene. The founder's complaint is not that the app lacks
handles in the abstract — it is that the gesture a modeller performs a hundred
times a day (grab the thing, pull it, watch it move) exists for precisely one
verb. Fillet radius, chamfer distance, hole diameter and depth, pattern spacing,
shell thickness, draft angle, datum offset and every sheet-metal length are the
*same physical gesture on different axes*, and `ExtrudeDragHandle` has already
solved the hard parts of it: the DOM-grip-over-GL-gauge split, the pointer→world
projection, the snap ladder, the keyboard slider, the token discipline.

**What is missing is the generalisation, not the invention.** Extract
`ExtrudeDragHandle` into a `<ParametricGauge>` that takes an anchor point, an
axis (linear or angular), a value, a setter and a unit, and the entire MODIFY
group becomes draggable in one wave. Angular values (revolve, draft, bend) want
the same object swept on an arc.

### P0-2 — Part workspace — clicking geometry in the 3D view selects nothing that survives the pointer moving

*Evidence:* `13-face-hover-and-offer.png` (pointer on the top face: full brass +
a `SKETCH ⏎` proposal chip) → `14-click-selects-nothing.png` (clicked that face,
moved the pointer 300 px away: the face is plain aluminium again, no readout, no
chrome change anywhere).
*Subtree:* `apps/web/src/viewport/**` + `apps/web/src/store/**`.

Measured: hover paints 52 875 px and a proposal chip; a click followed by
pointer-away restores the rest state exactly. `selection-readout` exists in
**one** file in the repo — `components/SketchStrip.tsx` — so the 3D workspace has
no selection readout at all. The product's own design spec says it out loud:
*"authoring a new click-to-select-geometry→tree binding (none exists today —
`ModelMesh` takes no `onClick`)"* (`docs/design/pre-selection.md`, scope
boundary).

Why this is the deepest finding in the audit: **it forces every command to be
modal.** You cannot pick three edges and then press F; you must press F, then be
asked for edges. That is Fusion's *pre-2010* flow, and it is the exact opposite
of Plasticity, whose whole feel is select-then-act with the selection persisting
across commands. Every "the next step is visible from the current state" test in
the mandate is unsatisfiable from the 3D view while this holds, because there is
no *state* for the next step to be visible from. It is also why the MODIFY tools
must all open empty, which is why they are all forms, which is P0-1.

It also produces a smaller, uglier symptom: **hover is louder than commitment.**
Pointing at a face is the most emphatic thing the viewport ever does.

### P1-1 — Viewport — the front, right and top orthographic views are an empty field

*Evidence:* `03-front-ortho-void.png` vs `04-front-persp-grid.png`;
`05-top-ortho.png`. Measurements in §3.
*Subtree:* `apps/web/src/viewport/**` (`AdaptiveGrid.tsx`).

Grid ink in the clear canvas region, front view: **7 514 px in perspective,
2 396 px in orthographic — and all 2 396 are the plate's own antialiased
silhouette**, not grid. Top-ortho retains three major lines at a luminance
invisible at normal gain. These are the three views in which an engineer checks
a part, and they are the three with the least on screen. Rule 3a(a) names this
defect by name.

Compounding it, and separately fixable: the **origin triad is off by default**
(the ORIGIN panel's six toggles all start hidden), so an axis-aligned view
offers no up, no origin and no scale.

### P1-2 — Viewport — a filleted body has no drawn edges at all and reads as clay

*Evidence:* `06-filleted-body-no-edges.png` (an 80 × 60 × 12 plate, 4 mm edge
break: zero line work anywhere) vs `07-sharp-body-edges.png` (same plate
unfilleted: silhouette, top-face perimeter and hole rims all drawn).
*Subtree:* `apps/web/src/viewport/**` (`ModelMesh.tsx`, `glbGeometry.ts`).

Root cause, from the source: `new EdgesGeometry(geometry, 25)`
(`ModelMesh.tsx:525`). That is a **mesh crease detector** — it emits a line only
where the dihedral angle between neighbouring *triangles* exceeds 25°. A fillet
is tangent by construction, so the boundary between the top face and the fillet
has a dihedral of ~0° and no line is drawn. The moment a part gets an edge break
— i.e. the moment it stops being a test cube and starts being a part — every
feature boundary disappears and the body renders as a soap bar. This is the
largest single gap between our render and Plasticity's, whose entire look is a
matte surface with crisp B-rep line work over it.

**The fix is cheap and the data is already on the client.** The tessellation
carries a per-face partition — `faceStarts(geometry)` / `subsetSurface()` in
`glbGeometry.ts` already walk it, and `setFaceMaterials` already groups draws by
face ordinal. A B-rep edge is therefore *derivable without the server*: the
boundary of each face's triangle set (an edge used by exactly one triangle
within that face), deduplicated across faces. Same buffer, one extra index pass,
no protocol change.

### P1-3 — Feature editors — seventeen identical stacked web forms, parked on the opposite side of the screen from the work

*Evidence:* `08-extrude-gauge.png` — the Distance field is at x 106 while the
thing it drives is at x 665. The seventeen editors are listed in §1b.
*Subtree:* `apps/web/src/components/**` (+ `packages/design/src/primitives/**`).

This is the surface where a modeller spends their authoring time and it is the
one surface in the product that reads templated: label-over-field rows, a
segmented control, a checkbox with a sentence, CANCEL | CREATE. It is also
*physically* far from the geometry: the eye is on the model, the hands are 550
px to the left.

**Proposed redesign, concretely enough to start:** the product already contains
the right primitive and uses it in the right place — `DimensionTag` /
`DimensionTagCell`, the ruled drafting strip the sketcher hangs on geometry
while you draw. Make that the editor. An open feature command renders its
parameters as **a ruled tag anchored to the geometry it is editing**, one strip,
terse caps label + value + unit stated once — `R 4 mm`, `Ø 6 · D 12 mm`,
`N 6 · 15 mm`. Tab walks the cells; Enter commits; Esc cancels; each numeric
cell that has a spatial meaning gets the `<ParametricGauge>` from P0-1 on the
geometry beside it. The left panel keeps only what genuinely is a *list* (edge
picks, profile references, the merge checkbox) and shrinks to a strip. That is
one distinctive idea, already in the design system, applied where the user is
looking — and it collapses seventeen bespoke forms onto one primitive.

### P1-4 — Extrude gauge — the drawn affordance is ten times the hit target, and its value cannot be typed

*Evidence:* §1c, measured by `elementFromPoint` down the gauge axis.
*Subtree:* `apps/web/src/viewport/**` + `packages/design/src/primitives/AxisGrip.tsx`.

The arrow body and arrowhead — the part a Fusion user grabs — return the bare
`canvas`, so pressing them orbits the camera. The grip is a 24 × 24 disc at the
point. And `readout=` makes the on-geometry value pointer-inert when the same
primitive's other mode is a real input. Two small changes turn the one good
handle in the product into a good one.

### P1-5 — Viewport — the cursor never changes over pickable geometry

*Evidence:* measured `getComputedStyle(canvas).cursor === "auto"` while hovering
a face that is highlighting brass. Repo-wide, there is no `cursor-` utility on
any viewport surface (`grep -rn "cursor-" apps/web/src/viewport/` → comments
only).
*Subtree:* `apps/web/src/viewport/**`.

The face lights up but the pointer does not commit to anything, so the surface
reads as a picture that happens to glow rather than as a control. Every
desktop modeller changes the cursor: crosshair in a sketch, a pick cursor over
selectable geometry, grab/grabbing over a manipulator. `DrawingSheet` already
does exactly this (`cursor: grab` / `grabbing` on the view grip) — the 3D
viewport is the one surface that does not.

### P1-6 — View navigation disappears in the two modes where orientation matters most

*Evidence:* `12-plane-pick-mode.png` (choosing a sketch plane: no ViewCube, no
ViewBar) and `11-sketch-dimension-at-creation.png` (inside a sketch: same).
*Subtree:* `apps/web/src/routes/**` + `apps/web/src/components/ViewBar.tsx`.

Rule 3a(b) calls persistent view navigation table stakes. It is present on the
part workspace and absent exactly when the user is deciding *which way the
world faces* — picking a plane — and when they most want to check a sketch
against the model in 3D. Fusion keeps the ViewCube up in every mode including
sketch.

### P2-1 — Design system — letter-spacing is 179 magic numbers, not a token

§4. `tailwind-preset.ts` has no `letterSpacing`; nine distinct arbitrary values
across the app. Fix the primitive: add a 3–4 step tracking scale
(`tracking-eyebrow` / `tracking-label` / `tracking-wordmark`) and sweep.
*Subtree:* `packages/design/**`.

### P2-2 — Tool band — the labelled group is the one nobody needed labelled

At 1920 px CREATE gains text; MODIFY and SHEET METAL (16 glyphs: fillet,
chamfer, pattern, shell, draft, hole, mirror, combine, 8 sheet-metal) stay
icon-only with 279 px of band unused. `01-hero-1920.png`.
*Subtree:* `apps/web/src/components/**` (`CreateStrip.tsx`, `TopToolbar.tsx`).

### P2-3 — Timeline — two different controls share one 24 × 47 box

`timeline-stop` (`role="slider"`, "Travel stop") and `rollback-slot-4`
(`button`, "Roll forward to the tip") both measure `24 × 47 @ (700, 753)`.
*Subtree:* `apps/web/src/components/TimelineStrip.tsx`.

### P2-4 — Inspector — the rebuild STATUS readout is below the fold at 1280 × 800

Present at 1920, scrolled out at 1280 where the TOPOLOGY *Edges* row is cut
through the middle. The readout that certifies the model is the one the laptop
frame hides. `02-hero-1280.png` vs `01-hero-1920.png`.
*Subtree:* `apps/web/src/components/**` (`InspectorPanel.tsx`, `BodyInspector.tsx`).

### P2-5 — View bar — projection is a sticky side effect, and Home does not restore it

Measured: at rest `Projection: perspective`; after **any** preset (front, top,
right, **iso**, **home**) it reads `Projection: orthographic` and never returns.
"Home view" should restore the home view, projection included.
*Subtree:* `apps/web/src/viewport/viewCommands.ts`.

### P2-6 — Viewport — no contact shadow and no ambient occlusion

`viewport.groundShadow` / `groundShadowOpacity` tokens exist; no shadow is
visible under the body in any captured frame (`07-sharp-body-edges.png` — the
plate floats). Bores show no darkening at depth. Both are what make Plasticity's
bodies sit in a place rather than hover in front of one.
*Subtree:* `apps/web/src/viewport/**` (`groundShadow.ts`).

### P3-1 — Export now exists at two addresses; the inspector copy is 320 × 82 px of duplicate

`part-export-band-{step,stl,3mf,glb}` in the top band (the 08-17 fix) AND
`part-export-{step,stl,3mf,glb}` in the inspector. Keep the band, keep the
inspector's *partial-file notice*, drop the four inspector cells.

### P3-2 — `view-projection`'s accessible name states its state, not its action

`aria-label="Projection: perspective"` on a toggle. Say what pressing does.

### P3-3 — ViewCube facet clicks re-orient but do not re-frame

A facet click left the body running off the bottom edge of the frame
(`16-viewcube-no-refit.png`). Fusion re-fits on a ViewCube pick.

### P3-4 — The sketch size tag's helper line wraps raggedly

*"Type a size · Tab switches · Enter"* / *"applies"* breaks mid-phrase at
1280 px (`11-sketch-dimension-at-creation.png`).

---

## 7. PROPOSED ROADMAP

Ordered so the earliest wave moves the "feels like a modeling tool" needle most
per unit of effort. Each item names ONE subtree, what the user sees change, and
how it would be PROVEN.

### WAVE 1 — "the scene looks like CAD" (viewport only, no state-model change)

The whole wave lives in `apps/web/src/viewport/**`. Nothing here touches the
data model, the API or any editor, so it can ship in parallel with everything
else — and it is the wave the founder will *see* first, because it changes every
frame of every part.

| id | title | subtree | user sees | proven by |
|---|---|---|---|---|
| **CRAFT-1** | B-rep edge overlay, derived from the face partition | `apps/web/src/viewport/**` | Every face boundary is drawn, including tangent ones. A filleted plate stops being a soap bar and reads as a machined part | **Pixel measurement**: count `viewport.modelEdge` ink on the filleted plate of `06-filleted-body-no-edges.png` — currently **0**; assert > 2 000 px and that the count does not collapse when a fillet is added. Plus a before/after screenshot pair on that exact fixture |
| **CRAFT-2** | The grid survives an axis-aligned orthographic camera | `apps/web/src/viewport/**` (`AdaptiveGrid.tsx`) | Front / right / top views show the ground plane (edge-on rule, or face-on grid) instead of a void | **Pixel measurement**: grid ink in the clear canvas region (x 336–944, y 104–640) at front-ortho ≥ 50 % of front-perspective. Today 2 396 vs 7 514, and all 2 396 are body AA |
| **CRAFT-3** | Origin triad visible by default, dimmed | `apps/web/src/viewport/**` (`OriginGeometry.tsx`) | An axis-aligned view still tells you up, origin and scale | **e2e**: `origin-axis-x/y/z` ink present at rest; the ORIGIN toggles still switch full emphasis |
| **CRAFT-4** | Cursor states on the viewport | `apps/web/src/viewport/**` | Crosshair in a sketch, pick cursor over selectable geometry, grab/grabbing on a manipulator | **e2e assertion**: `getComputedStyle(canvas).cursor` changes from `auto` on hovering a face, and reads `grab`/`grabbing` on the extrude grip. Today: `auto` throughout |
| **CRAFT-5** | Contact shadow + light ambient occlusion | `apps/web/src/viewport/**` (`groundShadow.ts`) | The body sits on the bench instead of floating; bores gain depth | **Pixel measurement**: mean luminance in a 40 px band directly beneath the body is below the background gradient's value at that height by ≥ 15 % |
| **CRAFT-6** | View navigation persists in sketch and plane-pick modes | `apps/web/src/components/**` (`ViewBar.tsx` mount point) | ViewCube + ViewBar never disappear | **e2e**: `view-cube` and `view-bar` present with non-zero boxes in the part, plane-pick and sketch modes at 1280 × 800 |

### WAVE 2 — "the numbers have handles" (generalise the one good manipulator)

| id | title | subtree | user sees | proven by |
|---|---|---|---|---|
| **CRAFT-7** | Fix the extrude grip: hit region = the drawn arrow; tag becomes an input | `apps/web/src/viewport/**` | You can grab the arrow anywhere along it, and type the depth on the geometry | **e2e**: `elementFromPoint` walked down the gauge axis resolves to `extrude-depth-handle` at ≥ 8 of 12 sample offsets (today 3 of 15); a real `page.mouse.click` on the arrowhead changes the distance. Plus `fill()` on the on-geometry tag |
| **CRAFT-8** | Extract `<ParametricGauge>` (anchor, axis, value, setter, unit, snap ladder) | `packages/design/**` + `apps/web/src/viewport/**` | Nothing yet — a primitive | **Unit tests** moved from `extrudeHandle.test.ts`; extrude re-expressed through it with the existing e2e still green (a pure refactor must not move a pixel — assert a screenshot match) |
| **CRAFT-9** | Linear gauges: fillet radius, chamfer distance, shell thickness, hole depth + Ø, datum offset | `apps/web/src/viewport/**` | Six more commands get a draggable arrow with the form as fallback | **e2e per verb**: drag the gauge N px, assert the editor's field changed AND the ghost preview redrew; keyboard arrows step the same value |
| **CRAFT-10** | Angular gauges: revolve angle, draft angle, edge-flange bend angle | `apps/web/src/viewport/**` | A swept arc handle with degree graduations | **e2e**: same shape, on `revolve-angle` / `draft-angle` |
| **CRAFT-11** | Pattern gauge: drag the last instance to set spacing, drag past to add count | `apps/web/src/viewport/**` | A pattern is laid out by dragging, not by typing two numbers | **e2e**: drag changes `pattern-spacing`; dragging past the next pitch increments `pattern-count` |

### WAVE 3 — "select, then act" (the structural one)

This is the largest item in the audit and the one that unlocks the mandate's
flow rules. It is deliberately third: waves 1–2 are cheap and visible, and this
one wants their primitives to exist first.

| id | title | subtree | user sees | proven by |
|---|---|---|---|---|
| **CRAFT-12** | Persistent geometry selection in the part workspace (`ModelMesh` gains `onClick` → a selection store) | `apps/web/src/store/**` | Clicking a face/edge keeps it lit after the pointer leaves; Shift adds; Esc clears | **e2e + pixel**: click a face, move the pointer 300 px away, assert the face's tint persists (today it reverts — `14-click-selects-nothing.png` is the before frame) |
| **CRAFT-13** | Selection readout in the part chrome, with a clear hover/selected contrast | `apps/web/src/components/**` | "1 face · 12.5 mm²" in the chrome; committed reads louder than addressed | **Pixel measurement**: chroma of a SELECTED face exceeds a HOVERED face by ≥ 30 %. Today they measure 53.6 vs 53.4 — indistinguishable |
| **CRAFT-14** | Pre-selection seeds commands (pick edges → press F → the fillet opens with them) | `apps/web/src/features/**` | Commands open filled in; the offer rail proposes the likely verb for what is selected | **e2e**: select two edges, open Fillet, assert `fillet-edges` count = 2 and Create is immediately reachable with zero further picks |

### WAVE 4 — "the editor is a tag on the work, not a form on the wall"

| id | title | subtree | user sees | proven by |
|---|---|---|---|---|
| **CRAFT-15** | Tag-on-geometry editor for the 1–2 parameter commands (fillet, chamfer, shell, datum) | `apps/web/src/components/**` | A ruled drafting strip anchored beside the geometry — `R 4 mm` — instead of a 200 px panel across the screen | **Screenshot pair** at 1280 × 800 + an **e2e** proving Tab/Enter/Esc and that the left panel no longer holds the value |
| **CRAFT-16** | Roll the tag editor out to the remaining thirteen, keeping list-shaped inputs (picks, profiles) in a strip | `apps/web/src/components/**` | One editing language across every verb | **e2e**: `editorSubmitReason` coverage preserved for all 17; reason-on-disabled still mouse- and keyboard-reachable |

### WAVE 5 — system + chrome repairs (cheap, parallelisable, any time)

| id | title | subtree | user sees | proven by |
|---|---|---|---|---|
| **CRAFT-17** | Tracking scale in the preset; sweep 179 arbitrary values | `packages/design/**` | Nothing — identical pixels, one source of truth | **Gate**: extend `scripts/check-tailwind-scale.py` to fail on `tracking-[…]` in `apps/web`; assert a full-page screenshot match before/after |
| **CRAFT-18** | Text labels for MODIFY + SHEET METAL at ≥ 1600 px | `apps/web/src/components/**` | The icons nobody can name get names where there is room | **Screenshot pair** at 1920; e2e asserting label text present ≥ 1600 and absent at 1280 |
| **CRAFT-19** | Separate `timeline-stop` from `rollback-slot-N` | `apps/web/src/components/TimelineStrip.tsx` | Two controls, two boxes | **e2e**: no two `[data-testid]` elements share an identical bounding box in the timeline |
| **CRAFT-20** | Rebuild STATUS pinned above the inspector's scroll | `apps/web/src/components/**` | The model's verdict is always on screen at 1280 × 800 | **e2e**: STATUS row visible without scrolling at 1280 × 800 |
| **CRAFT-21** | Projection is part of a named view; Home restores perspective; ViewCube re-fits | `apps/web/src/viewport/viewCommands.ts` | Home means home | **e2e**: after front→home, `view-projection` reads perspective; after a cube facet click the body's bbox is inside the canvas |
| **CRAFT-22** | Drop the duplicated inspector export cells; keep the partial-file notice | `apps/web/src/components/**` | One export address | **e2e**: `part-export-step` count = 1 |

### What this roadmap deliberately does NOT propose

- Rebuilding the **extrude command frame**, the **sketch dimension-at-creation**
  flow, the **rebuild-failure state**, the **modal tool bands**, or the
  **token/palette system**. All five are at or near the bar (§5).
- A new palette, a new type system, or a "modernisation" of the chrome. The
  chrome is the distinctive part of this product; the viewport is the generic
  part. Spending effort on the chrome would move the needle backwards.

---

## 8. RUNNING COMPONENT CHECKLIST (delta from this pass)

- 🔴 `Viewport` / `ModelMesh` / `AdaptiveGrid` — P1-1, P1-2, P1-5, P2-6
- 🔴 `ExtrudeDragHandle` — P1-4 (hit region, readout-only tag) — otherwise the best thing here
- 🔴 17 × `*Editor.tsx` — P0-1, P1-3
- 🔴 `store/**` selection model — P0-2
- 🔴 `ViewBar` mount point — P1-6, P2-5, P3-3
- 🔴 `TimelineStrip` — P2-3
- 🔴 `InspectorPanel` / `BodyInspector` — P2-4, P3-1
- 🔴 `CreateStrip` / `TopToolbar` — P2-2
- 🔴 `packages/design` tailwind preset — P2-1 (no tracking scale)
- ✅ `ViewCube` — present at 1280 × 800 and steers (08-17 P1-4 closed)
- ✅ `ExportToolGroup` — band placement correct (08-17 P1-1 closed)
- ✅ `HistoryErrorAlert` / `FeatureTreePanel` error rows / `ExportRow` partial notice — the failure state is exemplary
- ✅ `SketchScene` creation gestures + `DimensionTag` type-in-place
- ✅ Token discipline: 0 duplicated hexes between DOM and WebGL
- ✅ a11y floor: 80/80 named, every gate states its reason, brass focus ring, reduced motion honoured, no root overflow at 1280 × 800 or 1920 × 1200

## 9. COVERAGE THIS PASS DID NOT REACH

- Assemblies workspace and the drawings sheet editor (both were read in source
  for the manipulation census, neither was driven in the browser).
- Touch / tablet viewports — there is still no touch project in
  `playwright.config.ts`.
- The parts register and the empty/loading states (the 08-17 pass owns those,
  and a sibling auditor was on the creation journey this window).
- Long-content: very long feature names in the tree, > 20-feature timelines.
- Hover feedback on an EDGE was attempted and the probe point could not be
  confirmed to be on an edge; the claim is therefore not made.
