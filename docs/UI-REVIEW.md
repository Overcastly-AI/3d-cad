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

**Batch 1 — "the scene is a place" — ✅ SHIPPED 2026-07-16 (frontend-builder;
see the addendum entry below for evidence):**
1. ✅ Full-bleed canvas; tree + inspector become floating, collapsible overlays
   (shell restructure in `PartPage.tsx`/`AssemblyPage.tsx`).
2. ✅ Horizon-persistent grid (camera-scaled fade) + one-step-brighter grid
   tokens + background atmosphere (gradient/vignette) + ground contact
   shadow (deterministic baked pool — drei ContactShadows' per-frame depth
   pass rendered nothing in this stack and costs 3 passes/frame).
3. ✅ Studio shading preset: procedural token matcap ("machined aluminum under
   shop lights" — no external HDR, CSP-safe), stronger edge ink; the two
   hand-placed directionals are gone (the scene has no lights at all).
4. ✅ View navigation: token-skinned GizmoViewcube reference cube, bottom-center
   view rail (Home/Fit/Front/Top/Right/Iso), numeric snaps 1/2/3/4 + 0 + Home,
   zoom-to-cursor. Assembly fit race fixed (fit keys on LOADED geometry).
5. ✅ Side-by-side check against the Fusion/Plasticity framing recorded in the
   addendum below (mandate 3a-d).

_Post-review fixes (code-reviewer on `9767e17`, landed on top):_
- 🔴 **Camera teleport on mate authoring.** The loaded-geometry `fitKey`
  collapsed to `""` whenever a `doc_version` bump refetched the assembly
  evaluation (the `evalQuery` had no `placeholderData`), then repopulated —
  re-firing the auto-fit and snapping the camera off the angle the user
  orbited to in order to author the mate. Fixed with `keepPreviousData`
  (mirrors `ModelerPage`); regression spec holds the eval refetch open so the
  transient collapse commits (pre-fix reads `fit-auto`, post-fix stays `right`).
- 🟡 **Reference cube occluded by the right inspector.** A tall right panel
  drew over the bottom-right view cube (a table-stakes nav element) at
  1280×800. `FloatingPanel` right-side default clearance now clears the cube
  band; left panels keep the tight default.

**Batch 2 — "every element earns its place" (Tracks B + C quick wins) —
✅ SHIPPED 2026-07-16 (frontend-builder; see the addendum entry below):**
6. ✅ Wire-or-delete pass per the inventory table (KERNEL ×2/UNITS ×3/TREE/
   SOLVER/tagline/First-light chip all DELETED); FEATURES + INSTANCES + MATES
   counts folded into their section eyebrows.
7. ✅ `ToolButton` aria-disabled pattern — a gated tool now hovers + focuses and
   shows its reason to mouse AND keyboard; honest reason caption on every gate.
8. ✅ Group eyebrows render in the command band (Create/Modify/Inspect + the
   sketch band's Draw/Modify/Constrain/Finish); wordmark→home + register ›
   document › mode breadcrumb.
9. ✅ Sketch exit: idempotent finish (double-Escape can't mint a duplicate
   "Sketch1"), fresh-tree default naming.
   Command scoping (item 10's guard, pulled forward): an open editor LOCKS the
   band with a "Finish X first" reason — no more silent fillet→extrude pick loss.

_Post-review fixes (code-reviewer on `c83b43b`, landed on top):_
- 🔴 **The band lock was pointer-only.** The Create/Modify (H/D/P/S/L) and
  Measure (M) keyboard accelerators bailed on sketch `mode` but not on an open
  feature `editor`, so a single keystroke `setEditor(...)`'d over a live command
  and silently discarded its picks — the keyboard twin of the fillet→extrude
  loss the lock claimed to close. Both accelerator effects now also bail while
  `editor !== null`; new `nav-chrome` spec presses H/D/P/M against an open Fillet
  and asserts the command + picked edge survive (pre-fix the editor is swapped).
- 🟡 **`persistBuffer` could hard-lock sketch mode.** `planeRefFromSpec` ran
  outside the save `try`, so a throw skipped the `finally` that clears
  `creatingRef` → stuck `true` → every finish blocked, user trapped in sketch
  mode. Plane resolution moved inside the `try`; a defensive chain `.catch`
  clears the create guards so no freak error can wedge the sketch or the chain.

**Batch 3 — "in-command depth" (Track C structural + Track A follow-through)
— ✅ 10 + 11 (body/tree link) + 13 (hint) SHIPPED 2026-07-16; deferred slices
re-filed to BACKLOG (see the addendum below):**
10. ✅ In-command band state (open editor recedes the band to the active
    command + wired OK/Cancel; the editor-swap guard shipped in Batch 2).
11. ✅ Selection/hover feedback on the body + the tree→geometry link (hover
    glows the body's edges, selecting a feature warms it). 🔶 Per-face pick
    highlight + tree↔FACE linking DEFERRED — needs geometry-service
    face→feature attribution (OverlayResult carries none today).
12. 🔶 Live ghost previews — DEFERRED whole (avoid a half-built preview; datum
    cheapest, then extrude/pattern).
13. ✅ Empty-viewport first-run hint. 🔶 Origin triad + resting datum sheets +
    parts-home thumbnails DEFERRED (thumbnails need a snapshot pipeline).

### Component checklist

| Surface | Status |
|---|---|
| Viewport (grid/atmosphere/shading/nav) | 🔴 P0 ×4 — Batch 1 |
| Shell layout (panel columns vs full-bleed) | 🔴 P0 — Batch 1 |
| Assembly viewport (fit, mate HUD) | 🔴 P1 — Batch 1 |
| Command band (CreateStrip/SketchStrip/ToolButton) | ✅ Batch 2 (group eyebrows, aria-disabled reasons, in-command lock) + ✅ Batch 3 (in-command band state: recede to active command + wired OK/Cancel) |
| Inspector/title-block footers (both) | ✅ Batch 2 — decorative cells deleted, counts folded into eyebrows |
| Feature editors (all 7 forms) | ✅ forms sound + ✅ Batch 3 band scoping (in-command OK/Cancel) / 🔶 live preview DEFERRED (item 12) |
| Body selection/hover feedback | ✅ Batch 3 (hover glow + selected warm-tint, tree→geometry) / 🔶 per-face highlight + tree↔face DEFERRED (needs attribution) |
| Empty viewport | ✅ Batch 3 first-run hint / 🔶 origin triad + datum sheets DEFERRED |
| Feature tree panel | ✅ rows, status, rollback, errors / 🔴 footer cells |
| Sketch mode (strip, DRO, grid) | ✅ mode swap, DRO / 🔴 grid fade, exit semantics |
| Measure | ✅ functional; readout hierarchy P3 |
| Import STEP | ✅ honest states (busy/error/dismiss) |
| Parts/Assemblies home | ✅ functional / P3 thumbnails, delete-confirm |
| Sign-in | ✅ |
| A11y floor | ✅ (disabled-tooltip reachability fixed in Batch 2) |

Evidence: `docs/screenshots/ui-audit/*.png` (44 shots, desktop + laptop).
Re-audit with before/afters after each batch lands.

---

## 2026-07-16 — Makeover Batch 1 SHIPPED: "the scene is a place" (frontend-builder)

All five Batch-1 items from the audit above landed in one pass; Batches 2–3
remain open. What changed, per P0:

- **P0-4 shell:** the canvas is FULL-BLEED in all three workspaces (part,
  assembly, first-light). `FeatureTreePanel` / `BodyInspector` /
  `AssemblyTreePanel` / `AssemblyInspector` / `InspectorPanel` now float over
  the scene in a collapsible `FloatingPanel` (new component; collapse tabs
  carry `panel-collapse-*`/`panel-expand-*` testids). The sketch dead band is
  gone — the sheet runs edge-to-edge. Feature editors/HUD cards moved to a
  `left-editor` anchor (tokenized inset) clear of the floating tree.
- **P0-1 grid + atmosphere:** `AdaptiveGrid` (new, wraps drei Grid) scales
  `fadeDistance` with orbit radius every frame — the grid reads to the horizon
  at any zoom, world grid and sketch grid both. Grid tokens brightened
  (`gridMinor #232E3C`, `gridMajor #3E4D61`). The canvas is transparent over a
  token radial "skylight" gradient + a vignette overlay; a baked contact pool
  (`groundShadow` tokens) seats the body on the bench.
- **P0-3 shading:** bodies render with a PROCEDURAL studio matcap rasterised
  from four `viewport.matcap` token stops (Plasticity's technique; zero scene
  lights, deterministic, no HDR fetch — prod CSP forbids external assets).
  Same matcap for part bodies and assembly instances; assembly selection is a
  brass surface tint + brass edges. Edge ink darkened to `#333B46`.
- **P0-2 navigation:** drei `GizmoViewcube` re-skinned as a machinist's
  reference block (anvil faces, etch strokes, engraved mist labels, brass
  hover) with clicks routed through a view-command store so snaps respect
  `prefers-reduced-motion` (drei's own tween does not); a bottom-center view
  rail (`view-bar`: Home/Fit/Front/Top/Right/Iso, all wired, tooltips carry
  the shortcuts); numeric accelerators `1/2/3/4` + `0` fit + `Home`;
  `zoomToCursor` on the orbit controls. The camera rig stamps
  `data-view`/`data-camera-pos` on the viewport for QA.
- **P1 assembly fit:** the fit key is now the LOADED-geometry instance set
  (was: the instance-id set) — the camera frames the assembly when meshes
  actually land, never from stale/partial bounds; re-solves of the same set
  still never move the camera (the snap-together motion is preserved).

**Fusion/Plasticity side-by-side (mandate 3a-d), honest self-assessment.**
Reference framings: Fusion 360's default part workspace (light ground plane
+ horizon grid + ViewCube top-right + bottom-center nav bar + shaded-with-
edges bodies + named views) and Plasticity's dark workspace (matcap bodies,
mid-gray grid to horizon, minimal chrome). After Batch 1, Loft matches the
structural checklist: grid-to-horizon ✅, scene depth ✅, studio body shading
that models curvature at every angle ✅ (matcap, the Plasticity approach),
persistent view cube + named views + fit ✅, full-bleed scene with floating
panels ✅, zoom-to-cursor ✅. Remaining honest gaps to the incumbents:
no orbit-about-cursor / pivot-on-double-click (P2, Batch 3 scope), no
ortho-projection toggle, no selection/hover feedback on body topology outside
pick modes (P1, Batch 3 #11), no live editor previews (Batch 3 #12), no
empty-scene origin triad (Batch 3 #13), and the reference cube lacks
edge-labeled ortho rotation arrows Fusion has. Verdict: the viewport now
reads as a tool-grade scene, not a WebGL default; the depth gap left is
interaction (selection feedback, previews), not presence.

Evidence (committed): `docs/screenshots/viewport-makeover-{empty,body,sketch,
assembly}-{desktop,laptop}.png` (afters) vs `docs/screenshots/ui-audit/
{03-part-empty,07-body-default,06-sketch-drawn,23-assembly-two-instances}
-desktop.png` (befores). Full `just e2e` green including the new
`viewport-makeover.spec.ts` (view snaps drive the real camera; panels
collapse; assembly opens framed with both balloons on-screen).

---

## 2026-07-16 — Makeover Batch 2 SHIPPED: "every element earns its place" (frontend-builder)

All of Batch 2 (Tracks B + C) landed in one pass; Batch 3 remains. Answering
the founder's navigation ask ("are they organised · do they make sense · when
I click an icon does it only show relevant tools when enabled"):

- **Chrome — wire-or-delete verdict (Track B, all decorative cells resolved).**
  DELETED: KERNEL OCCT ×2 (a README fact styled as telemetry), UNITS mm ×3 (no
  unit system exists), TREE v2 (internal concurrency counter), SOLVER "Loft"
  (the product's own name dressed as a solver readout), the header marketing
  tagline, and the "First light" default chip. FOLDED into live section
  eyebrows: FEATURES → "Feature tree · N", INSTANCES/MATES → "Components · N" /
  "Mates · N". KEPT (all carry live values): mass-props/bbox/topology rows,
  STATUS, EXPORT strip, SOLVE, per-feature OK/ERR/SKIP + error rows. Every
  title-block footer now shows only cells that MOVE. ModelerPage owns its own
  "First light" chip (it IS that page), so the demo keeps its name without a
  decorative default leaking onto every screen.
- **Disabled tools speak (Track C P1).** `ToolButton` switched from native
  `disabled` (which set `pointer-events-none` + unfocusable — the reason
  tooltips were unreachable) to `aria-disabled`: a gated tool now HOVERS and
  FOCUSES and shows its reason ("Solve a sketch first" / "Create a body first")
  to mouse AND keyboard, while staying inert on click/Enter. Playwright's
  `toBeDisabled()` honors `aria-disabled`, so the gate assertions still hold.
- **Toolbar organised (Track C P2, founder "are they organised").** The band's
  Create/Modify/Inspect `role=group`s now RENDER their stamped eyebrows (the
  taxonomy was invisible before); the sketch band gained Draw/Modify/Constrain/
  Finish eyebrows and a two-tier status cell. The command band grew one tier
  (`commandBandHeight` 32→46). Every workspace got a `register › document ›
  mode` breadcrumb (part › Sketch / › Fillet …) and the LOFT wordmark is now
  the way home — a real route out of a workspace (browser-back was the only exit).
- **Command scoping — no silent state loss (Track C P1).** An open editor now
  LOCKS the whole band with a "Finish X first" reason and names the command in
  the breadcrumb, so clicking Extrude while a Fillet edge-pick is live can no
  longer silently discard the picks (Cancel/OK on the editor is the way out).
- **Sketch exit semantics (Track C P2).** `finishSketch`/`persistBuffer` are
  now idempotent for the unbound sketch (a create-in-flight guard + deferred
  exit), and the default name numbers off the FRESHEST tree — double-Escape
  during the async save can no longer mint duplicate "Sketch1" features.

**Gates.** `frontend-design` run; `just lint` + `just test` (py 1199 + web 517)
+ full Playwright (144 specs) green, incl. the new `nav-chrome.spec.ts`
(disabled-tool reachable by mouse AND keyboard with its reason; Fillet locks
Extrude and the picked edge survives a stray click; double-Escape mints exactly
one feature). Evidence (afters): `docs/screenshots/makeover-batch2-{band,
scoped,sketch}-{desktop,laptop}.png` + `-disabled-reason-desktop.png` vs the
`docs/screenshots/ui-audit/07-body-default-desktop.png` / `06-sketch-drawn-*`
befores. Founder gallery refreshed (`UPDATE_SCREENSHOTS=1`) so the committed
shots match the new band + breadcrumb + cleaned footers.

---

## 2026-07-16 — Makeover Batch 3 SHIPPED: "in-command depth" (frontend-builder)

The final makeover batch. Items 10, 11 (body/tree link) and 13 (hint) landed;
the attribution- and snapshot-blocked slices are re-filed to BACKLOG (below) —
quality over coverage, no half-built previews (the founder's own bar).

- **Item 10 — in-command band state.** An open editor now RECEDES the command
  band to an in-command bar: a brass `▸ <command>` indicator + wired **OK** /
  **Cancel** cells (Esc/Enter captions), the tool groups falling out of the
  visual band (kept `sr-only` in the a11y tree, still locked). OK is real — it
  runs the OPEN editor's OWN validated submit through a tiny command-action bus
  (`features/commandActions.ts`): the band bumps a nonce, the editor's
  `useCommandBridge(submit, canSubmit)` runs its Enter-path submit (added to all
  10 editors); Cancel closes the editor. The band reads "you are inside Fillet",
  not "the whole toolbar, greyed" — Fusion/Plasticity's in-command chrome.
- **Item 11 — body selection/hover feedback + the tree→geometry link.**
  Hovering the body brightens its B-rep edges (`viewport.hover`); selecting a
  feature in the tree WARMS the whole body — brass edges (`viewport.selection`)
  + a surface tint that multiplies the studio matcap toward brass
  (`viewport.selectedSurfaceTint`, shared with the assembly selection language —
  one source). Gated so a pick tool (measure/edge/face) always wins the
  viewport. QA hook `data-body-highlight` (none/hover/selected) on the viewport
  container. **Deferred:** per-face pick highlight + tree↔FACE linking — the
  merged GLB has no face groups AND `OverlayResult` carries no face→feature
  attribution, so "highlight Extrude1's faces specifically" needs a
  geometry-service slice first (out of frontend territory).
- **Item 13 — empty part.** A blank part now shows a first-run call to action
  ("Start with a Sketch — pick a plane, then draw · Or Import a STEP solid")
  centred in the horizon grid, cleared the moment work begins. **Deferred:**
  origin triad + resting datum sheets (coordinate-transform work) and
  parts-home thumbnails (needs a last-evaluated-mesh snapshot pipeline).
- **Item 12 — live ghost previews:** DEFERRED whole rather than ship a datum-
  only slice that reads as half-built.

**Fusion/Plasticity side-by-side (mandate 3a-d).** In-command chrome now matches
Fusion's (command name + OK/Cancel occupy the band, tools gone); body selection
reads like Fusion's rollover/selection warmth. Remaining honest gaps to the
incumbents: per-face hover highlight (Plasticity highlights the exact face under
the cursor — we highlight the whole body until face attribution lands) and live
parametric previews (item 12).

**Gates.** `frontend-design` run; `tsc` + eslint + prettier clean; web unit
517 green; Playwright `makeover-batch3.spec.ts` (5) + `nav-chrome` +
`viewport-makeover` + extrude/fillet/chamfer/datum slices green on the real
stack (isolated ports 8010–8012). Evidence (afters):
`docs/screenshots/makeover-batch3-{in-command,selected,empty}-{desktop,laptop}.png`
vs `docs/screenshots/ui-audit/{11-fillet-editor,17-extrude-editor,03-part-empty}-desktop.png`
befores.
