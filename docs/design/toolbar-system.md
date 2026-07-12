# Toolbar system — grouped icons + flyouts

Status: shipped (2026-07-11, frontend-builder); **density revision
2026-07-12** (founder feedback: too tall — the viewport is the hero). The
sketch toolbar is now a **single thin row** (~26 px, down from a ~110 px
two-panel stack). Grouping model, flyouts, icon set, and machine-shop tokens
are unchanged — only the vertical rhythm. Specifics of the revision:

- **One row, not two.** The former SKETCH row and CONSTRAIN row are merged
  into a single ruled Panel: status · draw tools · constraint families ·
  construction · finish. The `constraint-strip` sub-panel is gone; its
  `selection-readout` moved into the shared flat status cell.
- **No stacked label cells.** The two-line identity/action cells ("SKETCH /
  On XY", "SAVE SKETCH / 4 entities", "EXIT / Esc discards", "CONSTRAIN /
  …") are flattened. `sketch-step` + `selection-readout` sit on one gauge-face
  line ("On XY · 2 ent"); SAVE and EXIT and Construction are icon-only
  (`ToolButton` without `showLabel`) with their count/reason engraved in the
  tooltip (`caption`), so the entity count stays queryable under `sketch-save`.
- **Primitive-level padding trim.** `ToolButton` (`py-2`→`py-1.5`) and the
  `Flyout` trigger (`py-2`→`py-1.5`), and `ToolButton.caption` now renders in
  the tooltip rather than as a stacked second line — every toolbar thins
  uniformly (fix the primitive, not the instance).

Evolution of the
single-key-verb + text-strip pattern into a grouped **icon** toolbar with
**flyouts**, driven by the founder priority: ~13 keyboard verbs with real
letter collisions (tools L/R/C/A; constraints H/V/D/R/X/C/P/L/T/E/S/O + N),
and more coming (holes, patterns, sweep, measurement). Blend of **Fusion 360**
(logical Sketch / Create / Modify / Constrain grouping; dropdown galleries
under a group) and **Plasticity** (minimal, dark, icon-forward, deeply
keyboard-driven — icons are the discoverable surface, every tool keeps a
shortcut), rendered ON the existing machine-shop token system.

This is an **evolution, not a redesign.** What stays: the gun-blued carbide
palette, brass as the parametric-handle accent, Fragment Mono data face +
Hanken Grotesk UI, the title-block panel signature, and the viewport-as-hero.
What's added: a grouped-icon-toolbar + dropdown + hand-drawn icon layer that
carries the growing tool count without widening the strip past the viewport.

## Grouping model

**Sketch tools** (empty-selection verbs) — flat, always visible: Line (L),
Rect (R), Circle (C), Arc (A). The four primaries stay one keystroke / one
click away; they never fold into a menu.

**Constraints** (selection verbs) — three families behind labeled flyouts,
matching the taxonomy the constraint docs already use:

| Group        | Members (shortcut)                                          |
| ------------ | ---------------------------------------------------------- |
| Geometric    | Horizontal (H), Vertical (V), Parallel (P), Perpendicular (L), Tangent (T) |
| Dimensional  | Distance (D), Radius (R), Equal (E)                        |
| Relational   | Coincident (C), Concentric (O), Symmetric (S), Fixed (X)   |

Plus a standalone **Construction** toggle (N) — it is a mode flip, not a
family, so it stays a flat toggle button (and its `aria-pressed` is a QA hook).

**Feature creation** (Create group) — flat icon buttons: New sketch, Extrude,
Revolve. Fusion's Create/Modify split is the growth path: sweep/loft/hole land
in Create, fillet/chamfer in a future Modify group, each convertible to a
flyout gallery once the count warrants it.

## Interaction

- **Flyout** = a group trigger (icon + name + caret) opening a menu (`role="menu"`
  / `role="menuitem"`), keyboard-navigable: ArrowUp/Down roving focus,
  Home/End, Enter/Space to apply, Escape closes and returns focus to the
  trigger, Tab closes, outside-pointer closes. Each row shows the constraint
  icon, its name, and an engraved `Kbd` shortcut chip — the menu **teaches the
  keyboard**.
- **Keyboard survives untouched.** The global sketch key handler (PartPage) is
  the source of truth for accelerators; the toolbar never intercepts letters.
  Power users never open a flyout. The icons are the discoverable surface for
  everyone else. Shortcuts appear in every tooltip (`Kbd` chip).
- **Tooltips** appear on hover AND keyboard focus, sit below the top-anchored
  strip (never clipped), and are `aria-hidden` so the accessible name (which
  already carries the shortcut) isn't announced twice.

## Icon style

Hand-drawn, single-grid, inline SVG (`packages/design/src/primitives/icons.tsx`).
24-unit grid, 1.6 stroke, **square caps + miter joins**, `currentColor`
throughout — so the active (brass) state flows straight from the button's text
color, one palette, no per-icon color. The set is CAD-specific: dimension
lines, the statics ground symbol for Fixed, the bullseye for Concentric, a
dashed scribe for Construction, a datum-plane parallelogram for Sketch.

## Primitives (`packages/design`)

- `ToolButton` — icon (+ optional label, caption), shortcut chip in tooltip,
  `active` (brass scribe underline, `aria-pressed`), disabled states.
- `ToolGroup` — a labeled cluster (tracked-caps eyebrow + tight row).
- `Flyout` / `FlyoutItem` — the keyboard-navigable dropdown gallery.
- `Kbd` — the shortcut chip (brass on carbide, stamped like a gauge label).
- `icons.tsx` — the scribed glyph set.

Both crowded surfaces compose these: `SketchStrip` (tools + constraints) and
`FeatureTreePanel` (Create). One source; fix the primitive, not the instance.

## Self-critique — rejected as generic-SaaS-toolbar default

- **Lucide/Feather dependency** — rejected. The round-cap Feather vocabulary is
  the AI-default icon look and reads generic; most glyphs here are CAD-specific
  (the twelve constraints) and would be custom anyway, so a mixed set would look
  incoherent. Hand-drew a single scribed-grid set instead (square-cap/miter is
  the deliberate anti-default detail, tied to the "scribe line" token language).
  Bonus: no new dependency, no CSP question (inline SVG only — prod CSP forbids
  external asset requests).
- **Brass-filled active buttons / rounded pills / drop shadows** — rejected. The
  palette doc says brass is a *scribe line*, not a fill; filling shouts and
  breaks "chrome recedes." Active state is a 1px brass underline scribe on
  square-cornered, hairline-ruled cells — the title-block idiom.
- **A flat wall of 12 constraint icons** (pure Plasticity) — considered, rejected
  for the resting-width cost against viewport-hero and the founder's explicit
  "dropdowns." Family flyouts stay compact, scale to N constraints, and teach
  shortcuts on open.
- **Colorful Office ribbon** — rejected; violates the single-accent discipline.

## Test-hook / shortcut preservation

Every keyboard shortcut still fires through the unchanged global handler. All
data-testids preserved: `sketch-strip`, `constraint-strip`, `sketch-step`,
`selection-readout`, `tool-{line,rect,circle,arc}` (with `aria-pressed`),
`sketch-construction` (with `aria-pressed`), `sketch-save`/`sketch-exit`,
`plane-{XY,XZ,YZ}`, `new-sketch`/`new-extrude`/`new-revolve`. Constraint verbs
gained queryable `constraint-{action}` hooks on flyout rows and
`constraint-group-{geometric,dimensional,relational}` on the triggers. Full
`just e2e` (54 Playwright specs + geometry gates) stays green.

## Follow-up (not in this slice)

The other authoring surfaces still use the pre-icon text idiom and can convert
in a follow-up: the DRO, ExtrudeEditor/RevolveEditor op/direction toggles,
ExportControls, and the eventual Modify group (fillet/chamfer) + a sketch-tool
overflow flyout (slot/polygon/spline). Scope here is the toolbar system + the
two crowded surfaces so it stays reviewable.
