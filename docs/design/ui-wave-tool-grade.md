# UI Wave — design plan (frontend-design skill, 2026-07-30)

Founder brief: "should the timeline be at the bottom with a drag slider to
revert? what about component enablement/opacity? placement face looks like a
text box — shouldn't it know the face I selected? the frontend is not fully
hashed out. Needs to be comparable to Fusion 360 and Plasticity."

## Direction: extend, do not re-skin

The token system already carries a thesis (`tokens.ts:9`): **the machine shop,
not a SaaS dashboard** — gun-blued steel ground (`carbide`), machined-aluminum
model, scribed `brass` as THE single accent, signature = the "title block"
inspection panel. That thesis is good and established across 60+ components.

So this wave adds NO new palette, NO new typeface, NO second accent. Every new
surface is drawn in the existing hand. The design work is in **what structure
each surface encodes** — which is where all three current surfaces are lying or
mute.

Reused as-is: `SegmentedControl`, `Stamp`, `ContextMenu`, `Panel`, `NumberField`,
`ToolButton`, the full verb glyph set in `icons.tsx`, and the hover-reveal idiom
already at `FeatureTreePanel.tsx:330`.

---

## Surface 1 — the timeline

**What's wrong:** the rollback control is a 1px dashed rule inside the left tree
panel. A 1px line is not a scrub control, and a vertical list buries the one
thing that IS genuinely sequential.

**Why a sequence is honest here (not decoration):** feature order is *causal* —
feature N is evaluated against N−1's body. The existing `01 / 02` ordinals are
therefore truthful structure, not the generic numbered-marker tic. Horizontal is
the honest axis because the data is a dependency chain, and rollback is a
position along it.

**Metaphor (machine-shop true):** a **machine way with a travel stop.** Features
are op stations along a ruled way; the rollback marker is the travel stop that
limits how far the tool runs. That is literally what rollback does — it bounds
how far evaluation travels. Not a metaphor laid on top; a description.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ TIMELINE · 5                                                    ⇥ TO TIP   │
│                                                                            │
│   ┌────┐    ┌────┐    ┌────┐   ▐▛   ┌╌╌╌╌┐   ┌╌╌╌╌┐                       │
│   │ ▱  │────│ ⬆  │────│ ⌀  │───▐▌╌╌╌┊ ◗  ┊╌╌╌┊ ⌀  ┊                       │
│   └────┘    └────┘    └────┘   ▐▙   └╌╌╌╌┘   └╌╌╌╌┘                       │
│    01        02        03       ▲     04       05                          │
│   Sketch1   Extrude1  Hole1     │    Fillet1  Hole2                        │
│                          travel stop (drag / ← → )                         │
└────────────────────────────────────────────────────────────────────────────┘
```

- **Way line solid** between travelled ops; **dashed past the travel stop.**
  Dashed = "not present" is drafting convention and already our language in
  drawings HLR — so the encoding is consistent, not invented. Chips past the
  stop take a dashed outline too.
- Chips carry the **real verb glyph** (`HoleIcon`, `ExtrudeIcon`, …) — no new
  icon work. Ordinal in `font-data` tabular, name in `font-body`.
- Travel stop is the only brass element in the strip: it is the one position
  indicator, so it gets the accent and nothing else does.
- Error feature → glyph in `flag`. Suppressed → chip stippled, glyph at
  `gauge`. Both already exist as tree states; same vocabulary, new axis.
- Height 44px, chips ≥32px tall (touch floor). Drag the stop, or focus it and
  use ← →; `⇥ TO TIP` is the escape hatch back to "everything included."

**The one risk I'm taking:** the dashed-way encoding rather than plain grey-out.
Justified because it is drafting-true, it survives at 1440 and 1280, and the
chips dim as well so the cue is redundant, never load-bearing alone.

**Reuse:** `features/rollback.ts` (`barSlotIndex` / `rollbackIdForSlot`) is pure
index math and orientation-agnostic — it ports unchanged. Backend contract
(`rollback_feature_id` = last included feature) unchanged. Presentation only.

---

## Surface 2 — visibility / opacity / isolate

**What's wrong:** absent entirely. `BodiesPanel`, `FeatureTreePanel`,
`AssemblyTreePanel` have no show/hide, no opacity, no isolate.
`BodiesPanel`'s own docstring concedes it: "this stays a dense read-out."

**Restraint applies here.** The timeline gets this wave's boldness. Per the
CLAUDE.md mandate these panels are "quiet precision instruments," so these
controls are dense, keyboard-first, and revealed on hover/focus using the idiom
already at `FeatureTreePanel.tsx:330`.

**Deliberate anti-novelty choice — use the eye.** A novel glyph (aperture
square, filled/hollow swatch) would be more "designed" and would fail the
novice-UX bar the founder set ("could my grandpa follow it"). Visibility is a
*learned* symbol; convention wins. The design contribution is drawing it in our
hand — 1px scribe stroke, `gauge` → `mist` on hover — not inventing a dialect.

**Opacity is quantized, and that is the "remove one accessory" cut.** A
continuous slider in a 220px row is a fiddly target and nobody needs 0–100
granularity while modelling. Three stops — SOLID / GHOST / HIDDEN — via the
existing `SegmentedControl`. Continuous opacity, when someone genuinely wants
it, belongs in the inspector for the selected body, not in every row. That's
progressive disclosure, and it deletes a primitive rather than adding one.

```
BODIES · 2
  01  Body 1        Extrude1     👁   [SOLID│GHOST│HIDE]      ← on hover/focus
  02  Body 2        Import1      👁   [SOLID│GHOST│HIDE]
```

- **Isolate** is a verb, not an icon: it lives in the existing `ContextMenu`
  (right-click a row) with a shortcut, because it's infrequent and destructive
  to view state.
- Isolate needs a visible way back: an `ISOLATED` **`Stamp`** in the viewport
  with a dismiss. `Stamp.tsx` already exists.
- GHOST reads through the existing ghost token language (`tokens.ts` ghost set),
  so a ghosted body looks like the system's established translucency, not a
  second invention.

**Non-negotiable (mandate 3c):** every one of these must actually change the
render. A toggle that doesn't move a pixel in the WebGL scene is a defect, not a
stub. Wired to real viewport material/visibility state reading tokens — no hex.

---

## Surface 3 — feature editors

**What's wrong:** `HoleEditor` is 12 stacked form rows parked mid-frame. It
covers the viewport and shoves the model right (breaks "the viewport is the
hero"), and because the body scrolls, it hides the **single most important
input** — Placement face — above the fold while showing *C'sink angle*.

**The structural truth being missed:** a feature has **references** (what it is
attached to) and **parameters** (numbers). Those are different kinds of thing
and deserve different treatment. Losing sight of a reference is the actual
reported bug.

**So: references pinned, parameters scroll.**

```
┌─ NEW HOLE ──────────────────────────┐
│ FACE    Face 3 · Extrude1        ⟳ │  ← anchor block: pinned, never scrolls
│ POINT   24.5, −17.5, 10          ⟳ │     ⟳ = re-pick (the fallback, not the
├─────────────────────────────────────┤         primary way to fill it)
│ Ø   5.00 mm                         │  ← THE parametric handle, brass scribe
│ ───────────────                     │
│ Depth   [THROUGH ALL │ BLIND]       │
│ Type    [SIMPLE │ C'BORE │ C'SINK]  │  ← body scrolls; secondary params
│ ▸ Thread                            │  ← collapsed until wanted
└─────────────────────────────────────┘
```

- Docked to the **right rail** with the inspector, not centre-frame. Viewport
  keeps the middle.
- Anchor block is a compact 2-line title-block extension — it reuses the
  signature, doesn't compete with it.
- Thread block collapses (it was ~5 rows of the 12).

**And the behavioural half, which is the real fix (UI-W3):** the editor should
open with the anchor block ALREADY FILLED from what you selected. Today
`holePick` initialises `null` and `selectedFaceIndices` (`PartPage.tsx:1443`) is
never fed to the form, so you pick the same face twice. With pre-selection
consumed, the anchor block reads as *confirmation* rather than a to-do list —
which is exactly why Fusion feels immediate and this doesn't. Arming a pick
becomes the fallback for CHANGING a reference, not the way to set one.

---

## Quality floor (unstated, enforced)

WCAG-AA contrast on every new pair, visible focus on the travel stop and every
toggle, `prefers-reduced-motion` respected on the stop's drag transition,
responsive to 1280×800, all existing `data-testid` hooks preserved, new ones
added for the timeline/toggles. Judge against a Fusion/Plasticity reference
side-by-side before calling it done.
