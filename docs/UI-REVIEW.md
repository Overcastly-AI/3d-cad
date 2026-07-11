# UI Review

Design/a11y/consistency notes on the web app, owned by the **frontend-qa**
agent and fed by builder deliverables. Truth-only; screenshots over prose.

## 2026-07-11 — Toolbar system: grouped icons + flyouts (frontend-builder)

Shipped the grouped-icon-toolbar + dropdown + hand-drawn icon layer that
carries the growing tool count (~13 keyboard verbs, more coming). Full design
plan + self-critique: `docs/design/toolbar-system.md`.

- **Two crowded surfaces converted:** the sketch tool+constraint toolbar
  (`SketchStrip`) and the feature-creation toolbar (`FeatureTreePanel`).
  Constraints now group into Geometric / Dimensional / Relational flyouts
  (was a 12-cell text run that overflowed past the viewport at every width);
  Construction stays a flat toggle. Tools and Create verbs are scribed icon
  buttons.
- **Primitives** (`packages/design`): `ToolButton`, `ToolGroup`, `Flyout` /
  `FlyoutItem`, `Kbd`, and a hand-drawn CAD icon set (`icons.tsx`) — inline
  SVG only (prod CSP forbids external asset requests), no icon dependency.
- **Preserved the product:** every keyboard shortcut still fires through the
  unchanged global handler; all data-testids kept (+ new `constraint-{action}`
  hooks on flyout rows). Full `just e2e` — 54 Playwright specs + geometry
  gates — green. WCAG-AA ink, visible brass focus, keyboard-navigable menus,
  `prefers-reduced-motion` respected, holds at 1280×800.
- **Evidence:** `docs/screenshots/toolbar-system-{before,after}-{desktop,laptop}.png`,
  `toolbar-flyout-open-{desktop,laptop}.png`,
  `toolbar-feature-{before,after}-{desktop,laptop}.png`.

Open follow-up: convert the remaining text-idiom surfaces (DRO,
Extrude/Revolve editor toggles, ExportControls) and add the Modify group +
sketch-tool overflow flyout as the tool count grows.
