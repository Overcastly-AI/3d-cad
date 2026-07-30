# UI wave — tool-grade chrome (design decisions, 2026-07-30)

Decision record for the founder's 2026-07-30 recalibration. Read this before
implementing UI-W1…W5 (BACKLOG); it exists so the *reasons* survive, not just
the diffs. Companion to `toolbar-system.md` and `feature-tree.md`.

Founder brief, verbatim in substance: the timeline should be at the bottom with
a draggable marker to revert; components need enablement/opacity; "placement
face looks like a text box — shouldn't it know the face I selected?"; units and
mass should be controlled from a settings page like Fusion; planes, sketches and
bodies should be toggleable like Fusion; "the frontend is not fully hashed out."

## Direction: extend the thesis, do not re-skin

`tokens.ts:9` already carries a thesis — **the machine shop, not a SaaS
dashboard**: gun-blued steel ground (`carbide`), machined-aluminum model,
scribed `brass` as THE single accent, signature = the "title block" inspection
panel. It is coherent across 60+ components.

So this wave adds **no new palette, no new typeface, no second accent.** The
design work is in *what structure each surface encodes*, because that is where
the current surfaces are mute or lying.

Reused rather than reinvented: `SegmentedControl`, `ContextMenu`, `Panel`,
`NumberField`, `ToolButton`, the full verb glyph set in `icons.tsx`, the
hover-reveal idiom at `FeatureTreePanel.tsx:330`, and `Stamp` (landing in the
concurrent UI-P2 commit — treat as available, it was in flight when this was
written).

---

## 1. The timeline (UI-W1)

**Wrong today:** rollback is a 1px dashed rule inside the left tree panel. A 1px
line is not a scrub control, and a vertical list buries the one thing that is
genuinely sequential.

**Why sequence is honest here.** Feature order is *causal* — feature N evaluates
against N−1's body. The `01 / 02` ordinals therefore encode something true, and
horizontal is the honest axis because the data is a dependency chain with a
position along it. (Contrast the decorative ①② collisions filed in UI-REVIEW:
numbering is only earned when order carries information.)

**Metaphor, and it is a description rather than an ornament:** a **machine way
with a travel stop.** Features are op stations along a ruled way; the rollback
marker is the travel stop bounding how far the tool runs. Rollback literally
bounds how far evaluation travels.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ TIMELINE · 5                                                    ⇥ TO TIP   │
│   ┌────┐    ┌────┐    ┌────┐   ▐▛   ┌╌╌╌╌┐   ┌╌╌╌╌┐                       │
│   │ ▱  │────│ ⬆  │────│ ⌀  │───▐▌╌╌╌┊ ◗  ┊╌╌╌┊ ⌀  ┊                       │
│   └────┘    └────┘    └────┘   ▐▙   └╌╌╌╌┘   └╌╌╌╌┘                       │
│    01        02        03       ▲     04       05                          │
│   Sketch1   Extrude1  Hole1     │    Fillet1  Hole2                        │
│                          travel stop (drag / ← → )                         │
└────────────────────────────────────────────────────────────────────────────┘
```

- Way line **solid** through travelled ops, **dashed past the stop.** Dashed =
  "not present" is drafting convention and already our language in drawings HLR,
  so the encoding is consistent rather than invented. Chips past the stop take a
  dashed outline too — the cue is redundant, never load-bearing alone.
- Chips carry the **real verb glyph** (`HoleIcon`, `ExtrudeIcon`, …). No new icon
  work. DRY note: there is no shared verb→glyph map today (`CreateStrip` uses
  them inline, the tree renders verbs as text). Extract one map, three consumers.
- The travel stop is the **only** brass element in the strip: it is the only
  position indicator, so it takes the accent and nothing else does.
- Error → glyph in `flag`; suppressed → stippled chip, glyph at `gauge`. Same
  vocabulary as the tree, new axis.
- 44px strip, chips ≥32px (touch floor). Drag the stop, or focus and use ← →.
  `⇥ TO TIP` is the escape hatch back to "everything included."

**Ports unchanged:** `features/rollback.ts` (`barSlotIndex`,
`rollbackIdForSlot`) is pure index math with no orientation baked in, and the
`rollback_feature_id` contract (id of the last INCLUDED feature) does not move.
This is presentation only.

**The risk taken:** dashed-way encoding over a plain grey-out. Justified as
drafting-true, legible at 1440 and 1280, and redundant with chip dimming.

---

## 2. Visibility / opacity / isolate (UI-W2)

**Wrong today:** absent entirely. No `showDatum`, no sketch visibility, no
hidden-body set anywhere. `BodiesPanel`'s docstring concedes it: "this stays a
dense read-out." Datum planes and sketches **cannot be hidden at all**, which is
unreadable at five sketches and three datums.

**Scope is categorical, like Fusion's browser** (founder follow-up): Origin
(planes / axes / point), Sketches, Bodies — each folder toggleable *and* each
item individually; per-instance in assemblies.

**Restraint applies.** The timeline takes this wave's boldness. Per the design
mandate these panels are "quiet precision instruments," so the controls are
dense, keyboard-first, revealed on hover/focus via the existing idiom.

**Deliberate anti-novelty: use the eye.** A novel glyph (aperture square,
filled/hollow swatch) would look more designed and would fail the novice bar the
founder set ("could my grandpa follow it"). Visibility is a *learned* symbol;
convention wins. The contribution is drawing it in our hand — 1px scribe stroke,
`gauge` → `mist` on hover — not inventing a dialect.

**Opacity is quantized, and that is the cut.** SOLID / GHOST / HIDE via the
existing `SegmentedControl`. A 0–100 slider in a 220px row is a fiddly target and
nobody needs that granularity mid-model; what you reach for is solid / ghost /
hidden. Continuous opacity belongs in the inspector for the *selected* body,
where there is room to be precise. Progressive disclosure that deletes a
primitive instead of adding one.

```
BODIES · 2
  01  Body 1     Extrude1    👁   [SOLID│GHOST│HIDE]   ← revealed on hover/focus
```

- **Isolate is a verb, not an icon** — it lives in `ContextMenu` with a
  shortcut, because it is infrequent and destructive to view state.
- Isolate needs a visible way back: an `ISOLATED` `Stamp` in the viewport with a
  dismiss.
- GHOST reads through the established ghost token set, so a ghosted body looks
  like the system's own translucency, not a second invention.

**Non-negotiable (mandate 3c):** every control must move pixels in the WebGL
scene. A toggle that does not change the render is a defect, not a stub. Wire to
real viewport visibility/material state reading tokens — no hex.

---

## 3. Feature editors (UI-W3 + UI-W4)

**Wrong today:** `HoleEditor` is 12 stacked form rows parked mid-frame. It covers
the viewport and shoves the model right (breaking "the viewport is the hero"),
and because the body scrolls it hides the **single most important input** —
Placement face — above the fold while showing *C'sink angle*. That is why the
founder read it as a mystery text box: the control was off-screen.

**The structural truth being missed:** a feature has **references** (what it is
attached to) and **parameters** (numbers). Different kinds of thing, different
treatment. Losing sight of a reference is the reported bug.

**So: references pinned, parameters scroll.**

```
┌─ NEW HOLE ──────────────────────────┐
│ FACE    Face 3 · Extrude1        ⟳ │  ← anchor block: pinned, never scrolls
│ POINT   24.5, −17.5, 10          ⟳ │     ⟳ = re-pick (the FALLBACK)
├─────────────────────────────────────┤
│ Ø   5.00 mm                         │  ← THE parametric handle
│ Depth   [THROUGH ALL │ BLIND]       │
│ Type    [SIMPLE │ C'BORE │ C'SINK]  │  ← scrolls
│ ▸ Thread                            │  ← collapsed (was ~5 of the 12 rows)
└─────────────────────────────────────┘
```

Docked to the right rail with the inspector, not centre-frame. The anchor block
is a compact title-block extension — it reuses the signature, does not compete
with it.

**The behavioural half is the real fix (UI-W3).** Today `holePick` initialises
`null` and `selectedFaceIndices` (`PartPage.tsx:1443`) is never fed to the form,
so you pick the same face **twice**: once to select it, again after arming a pick
mode. With pre-selection consumed, the anchor block opens already filled and
reads as *confirmation* rather than a to-do list. Arming becomes the way to
CHANGE a reference, not to set one. This — not the styling — is the difference
between Fusion feeling immediate and this feeling like a form.

Applies to every reference-consuming editor: hole, fillet, chamfer, shell,
draft, sketch-on-face, datum.

---

## 4. Snapping (UI-W5)

**Wrong today:** only a **grid** snap exists — `SNAP_STEP_MM = 1`
(`sketch/store.ts:40`), toggled with `G`, hardcoded as a constant rather than a
setting. No endpoint / midpoint / center / intersection / tangent snapping in the
3D sketch (drawings do have vertex snap for dimensions). No modifier is used as a
live modal state anywhere: every `ctrlKey/metaKey/altKey` reference is a
shortcut bail-out guard, plus undo/redo.

**Polarity decision — snap is ON by default and the modifier SUPPRESSES it.**
The founder asked whether snapping is held with Ctrl/Cmd. Inverted deliberately:
if you must hold a key to get precision, you only get precision once you know
the feature exists, and a novice never finds it. Default-on means precision is
free and you opt out for the rare freehand placement. Fusion's Ctrl-suppresses
behaviour is the same call.

- A **glyph at the candidate** (▫ endpoint, ▵ midpoint, ⊙ center, ⨯
  intersection) names WHICH snap will be taken before commit. Never grab
  silently — a snap you did not see is a wrong dimension you will not find.
- **Ctrl/Cmd during placement = suppress.** Safe because our Ctrl bindings are
  keydown shortcuts, not pointer-drag. Alt is rejected: Windows/Linux window
  managers and browser menu focus contend for Alt+drag.
- **Shift = axis/ortho lock.**
- `G` stays the grid toggle; the step becomes configurable.

---

## 5. Settings, and the mass problem (#57, #58)

**No settings route exists** — zero hits for settings/preferences across all
routes. Length units are per-document via the top bar only.

**MASS PROPERTIES does not report mass.** The panel shows Volume, Area, Centroid;
there is no density and no material anywhere in the codebase, and
`geometry.py:240` documents centroid as "Centre of mass (mm)" while nothing
computes mass. This is the same overstated-surface class as the false CLASH badge
and the Tapped-checkbox drawing promise: **a surface asserting something it does
not have.** Until material/density lands, the panel title must not claim mass.

Mass needs a material library with density (kg/m³), per-document default with
per-body override, mass = Σ(volume × density), and assembly roll-up —
`assembly/evaluate.py` already composes volume analytically, so the hook exists.

**Sequencing:** a settings page is cheap, but most of what it would control does
not exist yet, so building the page first yields a shell with three rows. Ship
the rows whose properties are real (length unit, camera/mouse prefs, grid step)
and let material/density land into it after.

Missing settings, audited rather than guessed:

| Scope | Setting | State |
|---|---|---|
| Document | Length unit | exists (top bar only) |
| Document | Angular unit | missing — `units.ts` is length-only |
| Document | Display precision | `formatLength` takes max-digits, no user control |
| Document | Material + density → mass | missing; blocks mass entirely |
| Document | Grid / snap step | hardcoded `= 1` |
| App | Default units for new documents | missing |
| App | Camera: orbit style, invert scroll, pan/zoom speed | missing entirely |
| App | Keyboard remapping | missing |
| App | Origin-plane default visibility | missing |
| App | Graphics / visual style / edge display | missing |

The camera row is the sharpest: CAD users have strong muscle memory about orbit
and scroll direction, and a fixed binding with no invert is an adoption blocker.
It is also pure frontend.

---

## Quality floor (enforced, not announced)

WCAG-AA on every new pair, visible focus on the travel stop and every toggle,
`prefers-reduced-motion` on the stop's drag transition, responsive to 1280×800,
every existing `data-testid` preserved and new ones added for the timeline and
toggles. Judge screenshots side-by-side against a Fusion/Plasticity reference
before calling any of this done, and send them to the founder in chat — not just
into `docs/screenshots/`.
