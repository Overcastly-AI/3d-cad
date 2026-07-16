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

---

## 2026-07-16 — FULL AUDIT (founder recalibration — design mandate 3a)

**Trigger (founder, verbatim):** "I'm not in love with the front end. It
doesn't give me the Fusion 360 or Plasticity feel. Grid is not the full
screen. Certain elements are just for appearance rather than function. The UI
needs a full audit." Mid-audit scope expansion: "Audit the navigational
items. Are they organised. Do they make sense. When I click an icon does it
then only show relevant tool selection when enabled." A full makeover is
authorized — recommendations below are unconstrained by the current layout.

**Method.** Real stack on isolated ports (geometry :8012, documents :8011,
gateway :8010, Vite :5183), driven in real Chromium at 1440×900 (desktop) and
1280×800 (laptop). Every surface exercised: sign-in, parts home, empty part,
sketch mode (plane pick / rubber band / drawn), body workspace, all seven
feature editors, measure, keyboard pass, assembly (create → add instances →
mate HUD), reduced-motion. 44 evidence shots in
`docs/screenshots/ui-audit/` (audit evidence, not founder gallery). Source
cross-referenced for every finding.

### Executive verdict

The founder is right, and the gap is diagnosable. What shipped is a
**well-crafted dark dashboard wrapped around a debug viewport**. The DOM
chrome (title-block panels, brass accent, monospace readouts) is disciplined
and distinctive — but the 3D scene, which mandate 3 calls "the hero," is the
weakest surface in the product: a barely-visible grid that dies mid-frame
into flat black, a debug-gray box lit by two hand-placed lights, no view
navigation of any kind, no shadows, no atmosphere, no selection feedback on
the body. Fusion 360 gives you a horizon-anchored ground, a ViewCube, named
views, and shaded-with-edges materials before you draw anything; Plasticity
gives you matcap surfacing, cursor-centric navigation, and a scene that reads
as a *place*. Loft's viewport currently reads as a WebGL default with tokens.
Meanwhile several chrome elements are engraved like instruments but measure
nothing (KERNEL OCCT, TREE v2, SOLVER Loft, a static UNITS cell, a header
tagline) — precisely the "appearance rather than function" the founder named.
The navigation *bones* are good — the top band is genuinely mode-aware
(create ⇄ plane-pick ⇄ sketch strips) and the enable gates are mostly honest —
but disabled tools physically cannot explain themselves (their reason
tooltips are unreachable), open editors don't scope the band, and the
viewport itself never fills the frame because both side panels are subtracted
from the canvas instead of floating over it. **Verdict: the design system
survives; the viewport and the shell around it need the overhaul.**

### Findings

Severity: P0 = breaks the Fusion/Plasticity bar (mandate 3a), P1 = a working
engineer hits it in the first hour, P2 = quality/consistency debt, P3 = polish.

#### Track A — viewport presence & feel

- **P0 — Viewport — grid dies mid-frame into flat void** (the founder's
  literal complaint). `apps/web/src/viewport/Viewport.tsx:106-117` — drei
  `Grid` with `fadeDistance={420}`, `fadeStrength={1.2}`; the sketch grid
  repeats it at 340 (`apps/web/src/viewport/SketchScene.tsx:428-443`).
  Compounding it, the grid inks are near-invisible: `gridMinor #1B2330` on
  `background #0F141A` is ≈1.3:1, `gridMajor #2C3747` ≈2.2:1
  (`packages/design/src/tokens.ts:43-56`). Result: at the default fit the
  grid occupies the middle third of the frame and everything beyond it —
  most of the canvas — is undifferentiated black. Evidence:
  `07-body-default-desktop.png`, `03-part-empty-desktop.png`,
  `09-body-zoomout-far-desktop.png`. **Fix (primitive):** scale grid fade
  with camera distance (recompute `fadeDistance` from orbit radius, or
  `fadeFrom`/`fadeStrength` tuning) so the grid always reads to the horizon;
  raise grid token contrast one step; add scene depth — radial
  gradient/fog on the background token, subtle vignette, and a soft ground
  contact shadow under the body (drei `ContactShadows`). All token-driven.
- **P0 — Viewport — no view navigation at all.** Bare `OrbitControls` +
  one-shot auto-fit (`Viewport.tsx:127-131`, `FitCamera` at 12-45). No
  ViewCube/gizmo, no home view, no iso/front/top snaps, no fit-to-view
  command, no ortho/perspective toggle, no navigation hints anywhere. This is
  table stakes in every incumbent (mandate 3a-b). Evidence: every viewport
  shot; `10-body-orbit-low-desktop.png` shows how quickly a user gets lost —
  one drag produces a disorienting flat quad with no way home short of a page
  reload. **Fix:** drei `GizmoHelper` + `GizmoViewcube` (token-styled),
  keyboard view snaps (Fusion-style Home + F/T/R/Iso), a fit command, ortho
  toggle; persistent and quiet in a corner.
- **P0 — Viewport — debug-gray shading, no studio look.**
  `apps/web/src/viewport/ModelMesh.tsx:31-43`: one `MeshStandardMaterial`
  (aluminum token, metalness .35/roughness .55) under two directionals + an
  ambient (`Viewport.tsx:94-105`). No environment/matcap, no AO, and the
  B-rep edge ink `modelEdge #454F5B` disappears against large faces. At any
  non-hero angle the model is a flat untextured expanse — see
  `10-body-orbit-low-desktop.png` (a single gray quad, edges invisible) vs
  Plasticity's signature matcap that models curvature at every angle.
  **Fix (primitive):** matcap or `Environment` -based studio lighting as a
  token-declared preset ("machined aluminum under shop lights"), stronger
  edge ink, optional SSAO; kill the hand-tuned directional pair.
- **P0 — Shell layout — the viewport never actually gets the pixels.**
  `apps/web/src/routes/PartPage.tsx` (`<main>` flex row): the feature tree
  and inspector are 320 px *columns subtracted from the canvas*, not overlays
  — the canvas is ~800 px of a 1440 px frame (~640 px at 1280). The illusion
  of floating panels only exists because the column background equals the
  viewport background. The founder's "grid is not the full screen" is partly
  THIS: the scene literally ends where the columns begin (stark in sketch
  mode — the dead black band left of the sketch grid,
  `06-sketch-drawn-desktop.png`, is the reserved tree column). **Fix
  (makeover):** full-bleed canvas; panels float over it (Fusion/Plasticity
  pattern), collapsible, so every mode gives the scene 100% of the frame.
- **P1 — Assembly — default camera does not frame the assembly.**
  `23-assembly-two-instances-desktop.png` / `24-assembly-mate-hud-desktop.png`:
  with two instances (combined bbox 120×25×10 mm) the visible geometry is
  hard-clipped at the canvas edge and instance 2 is off-frame; the mate
  face-pick targets are half outside the viewport. `FitAssembly`
  (`apps/web/src/viewport/AssemblyScene.tsx:76-111`) refits only on the
  instance-SET key; when the fit fires before the freshly-added instance's
  GLB has loaded, the bounds it reads are stale/partial and there is no refit
  when the mesh lands. **Fix:** refit when loaded-geometry bounds change (or
  gate the fit on mesh readiness), plus a manual fit command (Track A item 2).
- **P1 — Part workspace — no selection feedback on the body.** Selecting
  Extrude1 in the tree brass-rules the row and opens the editor, but the
  solid in the viewport shows no highlight at all
  (`17-extrude-editor-desktop.png`); outside pick modes there is no
  hover/selection response on faces/edges. The tree and the geometry never
  point at each other. **Fix:** selected-feature highlight (tint the
  feature's faces via the existing overlay face data, or at minimum flash the
  profile sketch), and hover glow on pickable topology in every mode.
- **P1 — Feature editors — no live preview.** Extrude distance, datum
  offset, fillet radius, draft angle: nothing changes in the scene until
  CREATE/SAVE (`16-datum-editor-desktop.png` — a "New datum plane, offset
  30 mm" form with no ghost plane in the viewport). Incumbents preview every
  parameter live. This is the flip side of the founder's complaint: chrome
  that decorates while real *function* is missing. **Fix:** client-side ghost
  previews where cheap (datum plane, extrude prism from the solved profile,
  pattern transforms); debounced server preview for kernel ops later.
- **P2 — Orbit/zoom feel.** No zoom-to-cursor (OrbitControls dollies to
  target center), no orbit-about-picked-point; damping default. Feels
  floaty vs Plasticity's cursor-centric navigation. **Fix:** zoom-to-cursor
  + orbit pivot on double-click; expose in the same overhaul as the gizmo.
- **P2 — Empty part = black screen.** `03-part-empty-desktop.png`: no
  origin triad, no datum plane sheets at rest, no in-viewport call to action —
  the only guidance is 11 px text inside the tree panel. **Fix:** resting
  origin triad + quiet datum sheets + a first-run viewport hint.
- **P2 — Viewport keyboard alternative undocumented/absent.** Orbit/pan/zoom
  are mouse-only; no keyboard equivalents, no in-app navigation help.
  (Reduced-motion IS honored — damping off, `25-body-reduced-motion`.)

#### Track B — decorative chrome inventory (founder: "elements just for appearance")

Walked every tile/readout. Classification: functional (wired), informational
(honest but static), **DECORATIVE (defect per mandate 3a-c — wire or delete)**.

| Element | Where | Class | Disposition |
|---|---|---|---|
| Mass props / bbox / topology rows | `BodyInspector.tsx` | functional (real OCCT data) | keep |
| STATUS cell (Up to date/Solving/Error) | `BodyInspector.tsx:105-116` | functional, aria-live | keep |
| EXPORT strip (Ready/busy/error + STEP/STL) | `ExportRow.tsx` | functional | keep |
| **KERNEL OCCT cell** | `BodyInspector.tsx:99-104` + `InspectorPanel.tsx:112-117` | **DECORATIVE** — hard-coded brand string styled as a live readout | delete (it's a README fact, not telemetry) |
| **UNITS mm cell** | same footers ×2, `AssemblyInspector` | **DECORATIVE-adjacent** — dressed as a control/readout, but no unit system exists anywhere | delete until a real units setting ships, then wire as the entry point |
| **TREE v2 cell** | `FeatureTreePanel.tsx:211-218` | **DECORATIVE** — internal optimistic-concurrency counter, meaningless to an engineer | delete (keep in a debug flyout if wanted) |
| FEATURES count cell | `FeatureTreePanel.tsx:200-210` | informational but redundant (rows are numbered right above it) | fold into the panel eyebrow ("Feature tree · 2") |
| SOLVE cell (Solved/Failed/Solving…) | `FeatureTreePanel.tsx:219-230` | functional | keep, but see P1 selection-feedback — surface failures on the geometry too |
| **SOLVER "Loft" cell** | assembly inspector footer (`23-…png`) | **DECORATIVE** — the product's own name presented as a solver readout | delete or replace with real solve time/iterations |
| INSTANCES count cell | assembly footer | redundant with the components list | fold into COMPONENTS eyebrow |
| **Header tagline** "Parametric CAD · tessellated server-side by OCCT" | `TopBar.tsx:25-27` | **DECORATIVE** — marketing copy occupying prime toolbar space in a daily-driver tool | delete; reclaim for view controls or document status |
| "First light" default chip | `TopBar.tsx:23` | **DECORATIVE** leftover demo label | delete |
| Part-name chip | `TopBar` slot (`PartPage.tsx`) | informational, should be MORE functional | make it the breadcrumb (see IA) + inline rename |
| Sketch DRO (X/Y/SNAP/PLANE) | `SketchDro.tsx` | functional (live coords, snap toggle) | keep; PLANE cell duplicates the strip's "On XY" — drop one |
| Tree status badges (OK/ERR/SKIP + error rows) | `FeatureTreePanel.tsx` | functional, honest rebuild-failure surfacing (error code + message inline) | keep — this is the good pattern |

Verdict on the founder's instinct: **6 decorative elements confirmed**, all
"instrument-styled labels with nothing behind them." The signature
title-block language is worth keeping only where cells carry live values.

#### Track C — navigation / IA (scope expansion)

- **P1 — Disabled tools cannot explain themselves.**
  `packages/design/src/primitives/ToolButton.tsx:81` sets
  `disabled:pointer-events-none`, and disabled buttons are unfocusable — so
  the carefully-written reason tooltips ("Extrude — solve a sketch first",
  "Pattern — create a body first") are **unreachable by mouse and keyboard**.
  The founder's core question ("when I click an icon does it only show
  relevant tools when enabled") fails here: gating is correct, but the UI
  can't say *why* something is off. **Fix (primitive):** `aria-disabled`
  pattern (focusable, hoverable, inert on click) so the tooltip + reason
  caption always work.
- **P1 — An open editor doesn't scope the command band.** With the fillet
  editor open (radius focused, edge-pick session live), all 13 create/modify
  tools stay fully active (`11-fillet-editor-desktop.png`); clicking Extrude
  silently discards the fillet's picked edges (`PartPage.tsx` `openCreate*`
  all call `setEditor(...)` unconditionally). Nothing marks "you are in a
  command." **Fix:** while an editor is open, the band shows the active
  command + its OK/Cancel and recedes the rest (Fusion's in-command state);
  switching commands with unsaved picks prompts or is disabled.
- **P2 — Grouping exists in code, not on screen.** CreateStrip's groups
  (Create / Modify / Inspect) are real `role=group`s with aria-labels, but
  the `ToolGroup` eyebrow prop is unused — visually the band is a flat run of
  13 items separated by 1 px hairlines (`07-body-default-desktop.png`). An
  engineer can't see the taxonomy that's already there. **Fix:** render the
  eyebrows (or stronger group dividers with stamped labels); the primitive
  already supports it (`ToolButton.tsx:137-158`).
- **P2 — No route breadcrumb out of a workspace.** From `/parts/:id` or an
  assembly there is no UI path back to the registers — the part-name chip is
  inert, LOFT wordmark isn't a link, `WorkspaceNav` (Parts ⇄ Assemblies)
  renders only on the home pages. Browser-back is the only exit. **Fix:**
  wordmark → home; chip → breadcrumb (register / document, inline-renameable).
- **P2 — Sketch exit semantics: Escape silently persists, and can
  double-fire.** Escape's `exit` action calls `finishSketch` →
  `persistBuffer(true)` (`PartPage.tsx:641-648`, `sketch/tools.ts:376-387`) —
  drawn-but-unsaved work is committed with no save/discard choice. Worse,
  audit-driving Escape twice during the async save chain produced **duplicate
  features, all named "Sketch1"** (`06-sketch-drawn-laptop.png`: rows 01/02/03
  all "Sketch1" — the `Sketch${count+1}` naming also reads a stale tree).
  **Fix:** exit prompt (save/discard) or explicit ✓/✗ only; make
  `finishSketch` idempotent while a create is in flight; name from the
  freshest tree (server-side default naming would be DRY-est).
- **Mode legibility — mixed.** GOOD: the top band genuinely swaps per mode
  (create ⇄ "Pick a plane" ⇄ sketch tools — `04/06-sketch-*.png`), the
  measure HUD chip marks inspect mode, mate mode shows an instruction HUD.
  GAPS: the in-command state above; face/edge pick modes are only visible via
  cursor + overlay markers (no persistent "picking faces — Esc cancels"
  banner except mate's); and after the plane-pick step the only mode exit is
  keyboard Esc knowledge.
- **Enable/disable truth table (verified against state):** Import: enabled
  only pre-body ✓ (caption "A body already exists" — unreachable per the
  ToolButton bug). Sketch/Datum: tree-ready ✓. Extrude/Revolve: requires a
  solved sketch ✓. Sweep/Loft: ≥2 sketches ✓. Fillet/Chamfer/Pattern/Shell/
  Draft/Measure: require a body ✓. No enabled-but-inert tools found — the
  gating logic itself is sound; the failures are *communication* (reasons,
  grouping, in-command scoping), not truth.
- **P3 — Icon-only comprehension.** Sketch strip draw tools (line/rect/
  circle/arc/spline) read fine; trim/extend/offset/mirror/corner glyphs are
  cryptic without hover (`06-sketch-drawn-desktop.png`). Tooltips cover all
  on hover+focus. Acceptable for a keyboard-first sketcher; revisit labels
  when the strip is regrouped.
- **P3 — Parts home reads "website", not "tool".** Centered card + vast
  empty sheet, no part thumbnails, DELETE with no confirm
  (`02-parts-home-desktop.png`). Thumbnails (last-evaluated mesh snapshot)
  would make the register feel like a parts bin.

#### A11y floor (spot checks)

Focus rings: brass, visible, everywhere tabbed (`19-keyboard-focus-desktop.png`).
Reduced motion honored (orbit damping off). Contrast: DOM inks pass (mist
13.2:1, gauge 7.2:1); the failures are in the SCENE (grid tokens ≈1.3–2.2:1,
edge ink on aluminum) — covered by Track A. Roles/names: preserved
throughout, including flyouts. The one hard a11y defect is the unreachable
disabled-reason tooltips (Track C, P1).

### Remediation plan (ordered — a makeover spec, not nits)

**Batch 1 — "the scene is a place" (Track A core, all in
`Viewport.tsx`/`ModelMesh.tsx`/`SketchScene.tsx`/`tokens.ts`):**
1. Full-bleed canvas; tree + inspector become floating, collapsible overlays
   (shell restructure in `PartPage.tsx`/`AssemblyPage.tsx`).
2. Horizon-persistent grid (camera-scaled fade) + one-step-brighter grid
   tokens + background atmosphere (gradient/fog/vignette) + ground contact
   shadow.
3. Studio shading preset: matcap/env for bodies, stronger edge ink — the
   Plasticity reference; kill the two hand-placed directionals.
4. View navigation: ViewCube/gizmo (drei `GizmoHelper`), home/iso/ortho/fit
   commands + keys, zoom-to-cursor. Fix the assembly fit race while in there.
5. Side-by-side screenshot check against a Fusion/Plasticity reference
   before calling it done (mandate 3a-d).

**Batch 2 — "every element earns its place" (Tracks B + C quick wins):**
6. Wire-or-delete pass per the inventory table (KERNEL/UNITS/TREE/SOLVER/
   tagline/First-light chip); fold redundant counts into eyebrows.
7. `ToolButton` aria-disabled pattern — reasons reachable by mouse + keyboard.
8. Render group eyebrows in the command band; wordmark→home + breadcrumb chip.
9. Sketch exit semantics: save/discard prompt, idempotent finish, fresh
   naming.

**Batch 3 — "in-command depth" (Track C structural + Track A follow-through):**
10. In-command band state (active command + OK/Cancel, rest recedes; guard
    against silent editor swaps).
11. Selection/hover feedback on the body; tree↔geometry linking.
12. Live ghost previews (datum plane first — cheapest — then extrude/pattern).
13. Empty-viewport state (origin triad, resting datum sheets, first-run hint)
    + parts-home thumbnails.

### Component checklist

| Surface | Status |
|---|---|
| Viewport (grid/atmosphere/shading/nav) | 🔴 P0 ×4 — Batch 1 |
| Shell layout (panel columns vs full-bleed) | 🔴 P0 — Batch 1 |
| Assembly viewport (fit, mate HUD) | 🔴 P1 — Batch 1 |
| Command band (CreateStrip/SketchStrip/ToolButton) | 🔴 P1/P2 — Batches 2–3 |
| Inspector/title-block footers (both) | 🔴 P2 decorative cells — Batch 2 |
| Feature editors (all 7 forms) | ✅ forms sound / 🔴 no preview, no band scoping — Batch 3 |
| Feature tree panel | ✅ rows, status, rollback, errors / 🔴 footer cells |
| Sketch mode (strip, DRO, grid) | ✅ mode swap, DRO / 🔴 grid fade, exit semantics |
| Measure | ✅ functional; readout hierarchy P3 |
| Import STEP | ✅ honest states (busy/error/dismiss) |
| Parts/Assemblies home | ✅ functional / P3 thumbnails, delete-confirm |
| Sign-in | ✅ |
| A11y floor | ✅ except disabled-tooltip reachability (P1, Batch 2) |

Evidence: `docs/screenshots/ui-audit/*.png` (44 shots, desktop + laptop).
Re-audit with before/afters after each batch lands.
