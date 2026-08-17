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

_Post-review fixes (code-reviewer on `bde2b7b` — verdict approve-with-nits, no
🔴; the new command-action bus verified stale-closure-free + double-submit-safe;
both 🟡 landed on top):_
- 🟡 **Band OK cell now reads its true state.** It was always visually
  actionable even on an invalid form (silently inert — inconsistent with the
  editor's honest disabled Create cell, and against mandate 3a). The bridge now
  publishes the editor's `canSubmit` gate into the action store; the OK cell
  renders honestly `disabled` with a "Finish the form" caption until the form is
  valid. New spec: Draft (opens invalid) → OK disabled; Datum (valid) → enabled.
- 🟡 **Body selection highlight now yields to the pick tool.** `bodySelected`
  wasn't gated on `measureActive`, so arming Measure with a feature selected
  recolored the whole body brass and diluted the actual pick highlight. Gated
  on `!measureActive` — the pick tool wins the viewport (matching the hover
  half, which was already gated).

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
| Assembly BOM panel + SOLVE/PARTS toggle | ✅ PASS (spot-check cf617c8) / 2× P3 system-level below |

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

---

## 2026-07-16 — Drawings v1 spot-audit: sheet editor + register (commit 6671ec4)

Design-system / a11y / responsive / state-completeness review of the new
`/drawings` register + `/drawings/{id}` sheet editor (the paper-on-the-bench
signature). Geometry/layout MATH correctness is the parallel code-reviewer's;
this pass owns look-and-feel adherence. Evidence:
`docs/screenshots/drawings-editor-{1440,1280}.png`. Source read end-to-end
(`DrawingsPage`, `DrawingPage`, `DrawingSheet`, `DrawingCommandBand`,
`WorkspaceNav`, `Breadcrumb`, `drawing` tokens, `ToolButton`, `FloatingPanel`).

### Executive verdict

**Up to the makeover's standard — ship it; the open items are polish, not a
gate.** No P0/P1. The paper-on-bench inversion is executed exactly as the
mandate asks: spent boldly in one place, framed + drop-shadowed so it reads
deliberate (not an unstyled white box), and driven entirely from a proper
`drawing` token group that both renderers (Tailwind DOM + the SVG sheet) read
— zero hex literals in app code (grep clean). The register is a near-exact
structural sibling of `PartsPage` (same testid grammar, table, states, create
flow, `WorkspaceNav`), so the three homes read as one product. State coverage
is unusually complete. Contrast passes. The findings below are a short polish
list.

### Findings (prioritized)

- **P2 — sheet editor — the "Views" floating panel occludes the paper's
  top-right corner + its drawn border frame.** The opaque `anvil` panel sits
  over the sheet's top-right; at 1280 it clips the drawn border corner (visible
  in `drawings-editor-1280.png`), nicking the "framed sheet" read that makes
  the inversion feel deliberate. It clears the *views* (iso is centre-right, not
  in the corner), so no data is hidden — cosmetic, but it undercuts the one
  signature surface. Secondary: `FloatingPanel` reserves `max-h-[calc(100%-
  9.5rem)]` bottom clearance *for the r3f gizmo cube band* — but this 2D sheet
  has no gizmo, so the clearance is dead reservation. System fix: give the sheet
  container right-inset room equal to the panel width (or float the panel just
  outside the paper's right edge), and let the drawing route pass a tighter
  `maxHeightClassName` since there's no cube to clear.
  Ref: `drawings-editor-1280.png` (top-right), `FloatingPanel.tsx:35-38`.
  **✅ RESOLVED (orchestrator, with the code-review bounds-layout fix):** the
  sheet container now reserves a `lg:pr-[22rem]` right gutter so the paper never
  slides under the panel, and the Views panel passes
  `maxHeightClassName="max-h-[calc(100%-4.5rem)]"` (no gizmo cube on a 2D sheet).
  Refreshed `drawings-editor-1280.png` shows the full framed sheet clear of the
  panel.

- **P2 — sheet editor — command band invites setup actions while the drawing
  is still loading.** `DrawingPage` renders `DrawingCommandBand` (Part select /
  Scale select / "Lay out standard views") unconditionally, including while the
  `drawing` query is in flight and the bench shows the "Loading drawing…"
  centre note. `hasLayout` is `false` during load, so the pickers are live and
  "Lay out" can fire against `docVersion = 0` before the sheet's real version is
  known. Incoherent (band says "act", canvas says "loading") and a latent
  optimistic-concurrency race. System fix: gate the band's controls (or a `busy`
  flag) on `drawingQuery.isSuccess`, same as the setup hint is gated on `tree`.
  Ref: `DrawingPage.tsx:232-245, 137-138`.
  **✅ RESOLVED (orchestrator):** `DrawingCommandBand` now renders only when
  `drawingQuery.isSuccess`, so no setup action can fire against an unknown
  `doc_version`.

- **P3 — sheet — title-block captions render sub-legible at laptop width.**
  The `TITLE / SCALE / SIZE` captions are 2.3 mm SVG text; on the 1280 sheet
  (~3.0 px/mm) that's ≈6.8 px — under the practical floor for the mono face
  (the 3.4 mm values ≈10 px are fine). Contrast is not the issue (`drawing.label`
  #48525E on paper = 6.9:1, passes AA). Print-fidelity partly excuses fine
  print, but it's borderline. System fix: nudge the caption mm size up a step,
  or set a min effective px via a viewport-relative floor on the title block.
  Ref: `DrawingSheet.tsx:180-190`, `drawings-editor-1280.png` (title block).

- **P3 — command band — same `RectIcon` for two different verbs, and it
  doesn't read as "re-project".** "Lay out standard views" and "Re-project"
  both use `<RectIcon />`. A rectangle passes as a view-frame for *lay out*, but
  says nothing for *re-project/refresh* — the label carries all the meaning.
  System fix: add a refresh/reproject glyph to the design icon set for the
  post-layout action. Ref: `DrawingCommandBand.tsx:100-124`.

- **P3 — views panel — collapsed tab says "Views", expanded header says
  "Standard views".** `FloatingPanel title="Views"` (the collapse tab + aria
  name) vs `ViewsPanel` header "Standard views". Minor label drift on the same
  object. System fix: pass one string (use "Standard views" for both, or shorten
  the header to "Views"). Ref: `DrawingPage.tsx:324`, `DrawingPage.tsx:404`.

### Verified GOOD (no action)

- **Token adherence / one-palette-two-renderers.** New `drawing` group added to
  `tokens.ts` + surfaced in `tailwind-preset.ts` (paper/ink/label as closed
  DOM colors); the SVG sheet reads `drawing.*` + `font.data` + `viewport.
  atmosphere.abyss` for its seat-shadow — no hex in `apps/web` drawing files
  (grep clean). Stroke weights are mm design tokens, not per-element magic.
- **Inversion contrast.** ink #1B222B on paper #ECEFF2 = high; hidden-edge
  #6E7A88 = 3.8:1 (>3:1 graphical); label text 6.9:1 — all pass AA/1.4.11.
- **State completeness (unusually thorough).** Register: loading / error /
  empty / populated. Editor: drawing loading, load error, empty sheet (with a
  `hasParts` branch → "Create a part first"), projecting spinner, per-view
  "VIEW FAILED" stamp + `ViewsPanel` "failed", part-level projection-failure
  banner, layout-action error with a Dismiss. Long titles truncate at 22 chars.
- **a11y floor.** Sheet SVG is `role="img"` with a summarizing `aria-label`, and
  the per-view labels + live edge counts have a reachable DOM alternative in
  `ViewsPanel` (not locked inside the SVG). All interactive elements carry
  `focus-visible` brass outlines; `L` (lay out / re-project) and `N` (new
  drawing) keyboard verbs guard typing targets. Disabled "Lay out" explains
  itself to mouse AND keyboard via `ToolButton`'s `aria-disabled` (still
  hoverable/focusable) + `caption` reason — no pointer-events tooltip trap
  (mandate 7). Tooltip fade is `motion-safe:` gated; no ungated motion on the
  surface.
- **Chrome honesty (mandate 3a).** Every band/panel element is live: Part +
  Scale are readouts of real state post-layout, edge-count readouts are eval
  data, the legend is a functional key, Re-project is wired. Breadcrumb mode
  (`Set up` pre-layout → null after) is an honest mode indicator.

### Component checklist (delta)

- `DrawingsPage` register ✅ (near-dup resolved 2026-07-25: all three registers
  are one `DocumentRegister` + a copy config)
- `DrawingPage` editor 🔴 (P2 load-gating + panel occlusion)
- `DrawingSheet` SVG ✅ (P3 caption size only)
- `DrawingCommandBand` ✅ (P3 icon only)
- `drawing` token group ✅
- `WorkspaceNav` / `Breadcrumb` drawings parity ✅

---

## 2026-07-17 — Drawings v1 #6b: dimension authoring on the sheet (frontend-builder)

**Scope.** Dimension authoring on the drawing sheet — pickable projected edges
(blueprint-blue hover/focus), a type-gated author menu, drafting annotations
(extension/witness lines, dimension line, filled arrowheads, prefixed value),
a right-hand Dimensions list with model-true value + Delete. Commit `78ae196`
on `claude/open-source-3d-cad-o7hl49`. Method: source cross-read of
`DrawingSheet.tsx`, `dimensions.ts`, `DimensionAuthorMenu.tsx`,
`DrawingPage.tsx`, `tokens.ts`, plus pixel inspection of the founder shots
(`drawings-dimensioned-1440.png` / `-1280.png` vs `drawings-editor-1440.png`).

### Executive verdict

**Ships, with polish owed — not a blocker.** The dimensioning layer is real
(server-measured values, honest error/pending states, token-driven ink, one
palette across the SVG renderer) and reads *mostly* like an engineering print:
the weight hierarchy is right (dimension/extension lines are visibly thinner
than object edges), arrowheads are a slender drafting barb, the `Ø`/`R` prefix
and value stamp are legible on the vellum, and chrome honesty holds (every
panel/tile is wired to eval state, no decorative readouts). Two things keep it
from reading as a finished print: (1) the auto-placed `40.000` linear
dimension collides with the neighbouring view in the third-angle gutter, and
(2) the diameter value's opaque paper halo eats the top arc of the hole, so a
`Ø10` circle reads as a semicircle. Both are system-level (token/geometry)
fixes, not instance patches. a11y has one real gap: keyboard focus on a
pickable edge is visually identical to mouse hover.

### Findings

- **P1 — DrawingSheet / dimensions.ts — auto-placed linear dimension collides
  with the adjacent view in the inter-view gutter.** In
  `drawings-dimensioned-1440.png` the `40.000` linear sits in the narrow
  top↔front gutter: its value stamp lands *on* the FRONT view's top object
  line, and the dimension line runs near-colinear with that border — an
  ambiguous read (is that rule the dimension line or the view edge?). This is
  not a one-off: `dimensionOffsetMm = 11` is a *fixed* outboard offset, and in
  a third-angle layout the top view's bottom edge and the front view's top
  edge face each other across a shared gutter, so any width/length dimension on
  a gutter-facing edge is dropped predictably into that gutter. Manual drag is
  deferred for v1, which makes the fixed offset the *only* placement — so it
  must not routinely collide. Screenshot ref: `drawings-dimensioned-1440.png`
  (crop: the `40.000` between TOP and FRONT). **System fix:** make placement
  gutter-aware — clamp/flip the offset when the outboard side points at a
  neighbouring view's bounds (the layout already computes `viewBounds` per
  projection in `boundsAwareLayout`; feed sibling bounds into
  `buildDimensionAnnotation` so it can shorten/flip/stack the offset), or widen
  the standard inter-view spacing enough to seat a dimension. Until drag lands,
  a collision-avoiding auto-offset is the correctness bar.

- **P2 — dimensions.ts / DrawingSheet `DimensionGlyph` — the diameter value's
  opaque halo occludes the circle it measures.** The value is stamped at
  `c.y + (TXT*0.5 + 1)` — *inside* a Ø10 hole (r = 5 mm) — behind a
  `fill=drawing.paper opacity 0.92` rect (`haloW × haloH`). For a small hole
  the halo spans the upper arc, so the circle renders as a semicircle
  (`drawings-dimensioned-1440.png`, TOP view: the hole reads as a half-round).
  The value-on-paper halo is the right idea for keeping AA contrast off the
  graphite rules, but it must never mask *object* geometry. **System fix:** in
  the `diameter`/`radius` branch place the value clear of the circle (outside
  `r`, or leadered out) so the halo sits on empty paper; or paint the halo only
  under the annotation lines, never over the projected circle. Size-dependent
  (a Ø50 hole hides it), which is why P2 not P1 — but it's the demo hole, so
  it's the first thing the founder sees.

- **P2 — DrawingSheet `PickableEdge` — keyboard focus on a pickable edge is
  indistinguishable from mouse hover, and the focus ring is suppressed.** The
  interactive `<g role="button" tabIndex={0}>` carries `style={{ outline:
  "none" }}` and its `onFocus` merely sets the same `hover` state, so a
  keyboard user tabbing onto an edge gets the *identical* blueprint-blue
  recolor a mouse hover gives — no distinct focus affordance, and colour-only.
  It technically shows *a* state change (WCAG 2.4.7 scrapes by) but a keyboard
  user can't tell "focused" from "someone's mouse is over it," and on a dense
  sheet that's a real wayfinding loss. **System fix:** give the pick `<g>` a
  distinct focus treatment from the design tokens (e.g. a brass/`pickSelected`
  focus halo dot or a thicker outline ring) driven by a real `focus`/`hover`
  split, not the current merged flag; drop the blanket `outline: none`.

- **P2 — DrawingSheet / DimensionsPanel — the foreshortened (`~`) warning is
  explained only by an SVG `<title>` (mouse-hover), and the sheet/panel signal
  it inconsistently.** On the sheet a foreshortened value renders in
  `dimensionFlag` red with a `~` and a hover `<title>` ("dimension in a
  true-size view for the drawn length"); in the Dimensions panel the same
  dimension shows a bare `~` in normal `mist` ink with no explanation and no
  tooltip. So (a) the only explanation of what `~` means is mouse-reachable
  only — a keyboard/touch user gets a cryptic tilde (brushes the mandate-7
  "explain to mouse AND keyboard" rule), and (b) the same condition is red on
  the sheet but un-flagged in the panel. **System fix:** carry one
  foreshortened treatment across both renderers (flag ink in the panel too) and
  surface the reason in a keyboard-reachable way (a panel affordance / visible
  caption, not just SVG `<title>`).

- **P3 — DrawingSheet — pickable edges are only discoverable on hover; no
  resting affordance.** At 0 dimensions the sheet looks identical to the
  read-only editor — edges reveal their pickability only once hovered/focused.
  The Dimensions panel empty-state copy ("Click a highlighted edge…") is the
  sole cue and it lives in the right gutter, easy to miss. Consider a quiet
  resting hint that dimensionable edges are live (a one-time pulse, a
  cursor/legend cue, or a faint pick-tint) so a first-run user knows the sheet
  is interactive. Screenshot ref: `drawings-editor-1440.png` vs the hover
  state has no before-hover tell.

- **P3 — DimensionsPanel — rows don't associate a dimension with its view or
  locate it on the sheet.** A row is `TYPE · value · Delete` with no view
  column and no panel→sheet highlight link, so with several dimensions (or the
  same length in two views) you can't tell which edge a row names or find it on
  the paper. The sketcher/measure surfaces set a hover→geometry-highlight
  precedent (Batch 3). Fine to defer for v1's two-dimension demo; note for when
  the count grows.

- **P3 — DrawingSheet — every dimensionable edge is an individual tab stop.**
  On the demo plate that's a handful; on a real part it's dozens of SVG tab
  stops to page through before reaching anything else. Not a v1 blocker; flag
  for scale (a roving-tabindex or an "enter the sheet then arrow between edges"
  pattern is the eventual answer).

### What passes

- **Weight hierarchy / arrowheads / value stamp** read as drafting-standard:
  `visibleWeightMm 0.5` > `dimensionWeightMm 0.3` > `extensionWeightMm 0.25`
  is visible in the crops; the `3.4×0.9 mm` barb is a slender drafting arrow;
  `Ø`/`R`/bare prefixes format correctly; the diameter line is a full chord
  through centre with outward arrows (conventional). The `40.000`'s witness
  lines with gap + overrun are textbook.
- **Contrast (AA).** `dimensionText #1B222B` and `dimensionInk #2A3542` on
  `paper #ECEFF2` are ~13:1 / ~11:1; `pickHover #1E6FBF` ≈4.6:1 and
  `pickSelected #0F4C81` deeper — all pass AA for text and clear 3:1 for
  graphics; `dimensionFlag #B23A2E` ≈5:1.
- **Author menu a11y.** `role=menu`/`menuitem`, first item auto-focused,
  Up/Down wrap, Escape closes, brass `focus-visible` outline, `disabled` while
  busy — keyboard-authorable without a mouse. Type-gating (circle → Ø/R, line →
  linear) means an impossible combo is never offered.
- **Honest states.** Pending value `…`, measure error `unresolved`/red flag +
  an on-sheet dashed `!` marker with a `<title>`, per-view `VIEW FAILED`, the
  `part_error` alert banner — no silent wrong number. Empty Dimensions panel
  gives an instructive hint.
- **Chrome honesty (3a).** Every element is wired: STANDARD VIEWS edge counts +
  legend are eval data, DIMENSIONS count/rows/Delete are live, the panel
  collapse caret is a real control, the title block reflects real scale/size.
  No decorative tiles.
- **Responsive 1280.** `drawings-dimensioned-1280.png`: the sheet stays clear
  of the `lg:pr-[22rem]` panel gutter, dimensions remain legible, nothing
  clipped or overflowing the root. The gutter collision (P1) and halo occlusion
  (P2) persist at laptop width (same relative geometry) but no *new* responsive
  defect.
- **Reduced-motion.** Only colour transitions (`transition-colors
  duration-fast`) on edges/menu — no transforms/animation to gate; nothing to
  fault.

### Component checklist (delta)

- `DrawingSheet` dimension layer 🟡 — P1 gutter collision + P2 halo-occludes-circle + P2 edge focus==hover
- `DimensionAuthorMenu` ✅ — type-gated, keyboard-first, AA
- `DimensionsPanel` ✅ — honest states / P3 view-association + foreshorten parity
- `dimensions.ts` placement 🟡 — fixed offset collides (P1); diameter text placement (P2)
- `drawing` token group (dimension ink/weights/arrows + pick ink) ✅

### Resolution — frontend-builder fix pass (2026-07-17)

All four flagged P1/P2s (and the 🟢) fixed; the two deferred P3s + the
tab-stop-at-scale concern are filed to BACKLOG (P3). Evidence:
`docs/screenshots/drawings-dimensioned-{1440,1280}.png` (regenerated) — the
Ø10 hole renders as a FULL circle with `Ø10.000` clear to its right, and
`40.000` seats in the widened gutter clear of the FRONT view.

- **P2 diameter halo masked the arc → RESOLVED.** `dimensions.ts` diameter
  branch stamps the value beyond the arc along the dimension line (outboard,
  obstacle-aware side); the paper halo now lands on empty paper. (Radius text
  pushed out by its half-width for the same reason.)
- **P1 gutter collision → RESOLVED.** `buildDimensionAnnotation` takes
  sibling-view SVG bounds (`obstacles`) + sheet extent and flips the offset off
  an occupied side (`chooseByPenalty`); `viewContentSvgRect` supplies them and
  `VIEW_GUTTER_MM` 14→24 guarantees clearance. Unit test covers the flip.
- **P2 focus==hover → RESOLVED.** `PickableEdge` splits `hover`/`focus`;
  focus adds a distinct deep-blue RING (`drawing.pickFocusRingMm`) under the
  edge (a shape change, not colour-only); blanket `outline:none` replaced by the
  custom ring.
- **P2 `~` mouse-only/inconsistent → RESOLVED.** The Dimensions panel flags a
  foreshortened value in the same flag ink as the sheet and carries an
  always-visible (keyboard/touch-reachable) legend explaining `~`.
- **🟢 `DimensionAuthorMenu` shadow → RESOLVED.** Now the `shadow-float` token.

Checklist now: `DrawingSheet` dimension layer ✅ · `dimensions.ts` placement ✅.

---

## 2026-07-17 — Spot-check: Units U2 (document length-unit system) — commit `fb26305`

Static/token + a11y review (live stack unbootable in sandbox — Docker registry
403; render-level checks below are CI-deferred and noted as such). Scope: the
new `InlineSelect` primitive, `DocumentUnitSelect` chrome, and the unit-suffix
propagation across feature editors, the mate HUD, `MeasureReadout`, and the
`mate-value-echo`.

### PASS

- **`InlineSelect` primitive** (`packages/design/src/primitives/InlineSelect.tsx`)
  — disciplined instrument, no findings. Tokens only (`border-etch`,
  `bg-carbide`, `text-gauge`, `text-mist`, `outline-brass`, `bg-anvil`,
  `font-display`/`font-data`, `text-2xs`/`text-md`) — no hex, no raw-element
  restyle. Built on a **native `<select>`** so it is keyboard-operable and
  screen-reader-correct for free; the `eyebrow` span is `aria-hidden` and the
  accessible name comes from `aria-label ?? eyebrow` (no double-labeling).
  Visible focus via `focus-within:outline-2 outline-offset-1 outline-brass`.
  Contrast AA in both themes (mist 13.2:1 / gauge 7.2:1 on carbide/anvil). Quiet
  ruled pill — reads as chrome, not a marketing dropdown.
- **`DocumentUnitSelect`** (`apps/web/src/components/DocumentUnitSelect.tsx`) —
  `aria-label="Document length unit"`, `data-testid` preserved, transient
  `disabled` during the PATCH (sub-second, no explain-tooltip needed).
  **Placement is consistent** across both editors: in `TopBar` immediately after
  `Breadcrumb` (chrome, not viewport — hero layout untouched), identical props
  in `PartPage` and `AssemblyPage`.
- **Feature editors + mate HUD** — every dimension cell now feeds
  `unit={docUnit}` into `NumberField`, which renders the unit as a lowercase
  value-adjacent suffix span (`font-body text-xs text-gauge`). Uniform
  placement/casing/spacing across Extrude/Fillet/Chamfer/Shell/Draft/Datum/
  Pattern/offset-plane and the mate HUD field. Stale `aria-label="… (mm, signed)"`
  hardcodes correctly dropped for `"… (signed)"`.

### Findings

- **P3 — `MeasureReadout` / unit-label presentation — the readout is the odd
  surface out — `apps/web/src/components/MeasureReadout.tsx:135-155`
  (render-visual, CI-deferred to confirm on screen).** Every other unit-bearing
  surface (feature cells, mate HUD field, `mate-value-echo`) shows the unit
  **lowercase, adjacent to the numeral** (`25.4 mm`). `MeasureReadout` instead
  folds the unit into the **eyebrow caption** (`Distance · ${unit}`,
  `Δx · ${unit}`), and that eyebrow carries `uppercase`, so `mm`/`in`/`m` render
  as `MM`/`IN`/`M`. Two issues: (a) placement diverges from the app-wide
  value-adjacent convention; (b) uppercasing mangles case-sensitive unit symbols
  — `m` (metre) → `M` collides with the SI mega prefix. Reads templated against
  the "quiet precision instrument" mandate. **System-level fix:** adopt one
  readout convention — keep the eyebrow as the bare quantity ("Distance", "Δx")
  and stamp the unit lowercase adjacent to the value (a shared readout suffix),
  matching `NumberField`/`formatLength`. Fold the minor angle-spacing nit below
  into the same convention.
- **P3 (minor, fold-in) — degree-symbol spacing inconsistent — `MateHud.tsx:99`
  vs `mates.ts` `mateDetail` / `formatAngleDeg`.** The mate HUD renders `°` as a
  `gap-1` suffix span (a space before the glyph: `45 °`), while `mate-value-echo`
  and the measure readout set it tight (`45°`, `45.0°` — the conventional
  typographic form). Normalize to tight `°` when the shared readout convention
  above lands.

### Component checklist (delta)

- `InlineSelect` primitive ✅
- `DocumentUnitSelect` chrome ✅ (placement consistent part/assembly)
- Feature-editor unit suffixes ✅ (uniform lowercase, value-adjacent)
- `MeasureReadout` unit presentation 🟡 — P3 eyebrow-uppercase + placement divergence
- `mate-value-echo` / `mateDetail` ✅ (lowercase suffix; P3 `°` spacing nit only)

### Resolution — orchestrator fix pass (2026-07-17)

Batched with the `code-reviewer` findings on the same slice.

- **FIXED — `MeasureReadout` unit presentation** (the P3 above): `len` now formats
  with the unit suffix (`formatLength(mm, unit, {unitSuffix: true})` → `25.4 mm`,
  lowercase, value-adjacent, in the `font-data` value span — not the uppercase
  eyebrow); the four eyebrows dropped to bare captions (`Distance`, `Δx`/`Δy`/`Δz`).
  Kills the `m`→`M` SI-prefix collision and aligns the readout to the app-wide
  convention.
- **FIXED — stale `(mm)` aria-labels** (`code-reviewer` 🟡, WCAG name/label
  mismatch that the PASS note above missed): `DraftEditor.tsx` neutral-plane
  offset + `SketchStrip.tsx` offset-plane distance now interpolate the doc unit
  (`(${unit}, signed)`), so the accessible name tracks the visible suffix.
- **FIXED — imperial seed precision** (`code-reviewer` 🟢, a correctness item, not
  cosmetic): `lengthInputValue` seeded at 4 fraction digits quantised an inch/foot
  value by > the 1e-4 mm kernel tolerance, silently shifting geometry on an
  unchanged re-save. Now unit-aware (`ceil(log10(mm-per-unit)+5)` digits,
  round-trip ≤1e-5 mm), covered by `apps/web/src/units/length.test.ts` (35 cases).
- **DEFERRED (filed, P3 cosmetic) — degree-symbol spacing** (`MateHud.tsx:99`):
  the `°` sits a `gap-1` space off the numeral (`45 °`) vs tight elsewhere (`45°`).
  Left for a deliberate `NumberField` pass — tightening it means teaching the
  shared primitive that symbol-suffixes (`°`) hug the value while worded units
  (`mm`, `in`) keep their space; that's a primitive-level design call, not a
  casual polish edit.
- **DEFERRED (filed, P3 cosmetic) — revolve axis-candidate label** (`revolve.ts`
  `axisLabel`): the picker labels each eligible sketch line with its length in raw
  `mm` regardless of doc unit. It's a line *identifier*, not an editable/measured
  value, so it sits just outside the "readouts format the same way" contract;
  route through `formatLength` when the revolve module is next touched.

## 2026-07-17 — Spot-check: Undo/Redo UR2 (History ToolGroup + shortcuts) — commit `6f33d94`

Static/code + token review (compose stack can't boot in this sandbox); render
checks marked CI-deferred. Scope: `packages/design/src/primitives/icons.tsx`
(UndoIcon/RedoIcon), `apps/web/src/components/CreateStrip.tsx` (History group),
`apps/web/src/routes/PartPage.tsx` (wiring + chord handler).

**What's right (evidence, not vibes):** icons inherit the house frame exactly
(24-grid, 1.6 stroke, square-cap/miter via the shared `Icon` wrapper,
`currentColor`); ink density (~40 grid-units) sits mid-family (Trim ~43,
Sketch ~45); the chevron arrowhead's 4√2 arms match `SymmetricIcon` precedent;
Redo is a true mirror of Undo about x=12. A11y: explicit `aria-label="Undo"` /
`"Redo"` keeps the shortcut chip out of the accessible name; gating rides the
band's `aria-disabled` ToolButton pattern (still focusable, reason caption on
hover AND focus-visible — no `pointer-events-none` trap); `locked` state uses
the same `captionFor` lock reason ("Finish Fillet first") as every other tool;
`motion-safe:` on the tooltip transition; e2e asserts names + gates at every
history bound. Chord grammar correctly leaves ⌘Y to the platform and native
undo to focused text fields; buttons are wired to real server `can_undo`/
`can_redo` state — no decorative chrome.

- **P2 — CreateStrip band width at the 1280×800 floor —
  `apps/web/src/components/CreateStrip.tsx` History group + `ToolButton`
  `showLabel` sizing — screenshot: CI `undo-redo-band-desktop.png`
  (render-verify; finding is arithmetic).** The band is a no-wrap flex row
  (`TopToolbar` → `divide-x` groups). Pre-change natural width ≈ 1236 px
  (13 labeled buttons: 48 px fixed + ~7.2 px/char labels at `text-2xs`
  Fragment Mono, group padding, dividers) — fit at 1280 with ~44 px spare.
  The History group adds ~170 px → ≈ 1405 px natural width, ~125 px over the
  1280 floor. Best case the `min-w-0 truncate` chain ellipsizes most labels
  (~1 char each: "EXTRUD…", "CHAMBE…"); worst case (if any flex item's
  `min-width:auto` doesn't resolve through) the Inspect group clips off-frame.
  Either way this commit is the one that tips it. **System-level fix:** shed
  labels responsively at the primitive level, not per-instance — e.g. a
  container-query tier on `ToolGroup`/`ToolButton` that drops `showLabel`
  below a band-width threshold; or ship History icon-only outright (undo/redo
  arrows are the two most self-evident glyphs in software; Fusion shows them
  unlabeled) which recovers ~90 px, plus icon-only Measure (~45 px) to clear
  the floor. Verify with the CI screenshot before and after.
- **P3 — busy-caption claims the wrong direction — `CreateStrip.tsx:276-293`.**
  While `historyBusy` (either operation in flight) BOTH buttons disable, and
  each shows its own verb: click Undo, hover/focus Redo → tooltip reads
  "Redoing…" though nothing is being redone (and vice versa). Honest-chrome
  nit: the reason shown must be the true reason. Fix: thread which step is in
  flight (PartPage already knows) and caption the idle partner "History busy…"
  (or reuse the in-flight verb only on the button that owns it).
- **P3 — icon doc-comment vs geometry — `icons.tsx:595-612`.** The section
  comment sells "hard-elbow returns … not the round-cap circular-arrow of the
  office icon sets", but both glyphs return through a 4.5-unit semicircular
  arc (`A4.5 4.5`) — a round hook; only the caps/joins are square. Visually it
  still reads scribed (square caps do the work at 16 px), but it sits closer
  to the generic "reply" arrow than the comment claims. Either sharpen the
  return to a true elbow (`H…V…H…` — would rhyme with Perpendicular/Mirror's
  L-bends and buy real distinctiveness) or fix the comment to match the ink.
- **P3 — shortcut chips aren't platform-aware — `CreateStrip.tsx:273,287`.**
  First multi-key chords in any chip ("Ctrl+Z", "Ctrl+Shift+Z"); on macOS the
  canonical chord is ⌘Z/⇧⌘Z (the handler accepts `metaKey`, so function is
  fine — the label just teaches the wrong hand position). Single-letter chips
  elsewhere dodge this. **System-level fix:** a shared `formatChord()` helper
  (platform-detect → `⌘Z` vs `Ctrl+Z`) feeding `Kbd`, so future chord chips
  (there will be more) inherit it. Note the Redo chip also can't advertise the
  bound `Ctrl+Y` alias — acceptable, the chip shows the primary chord.
- **Pre-existing (not this commit, noted for the running list):** the
  ToolButton tooltip (title + reason caption) is `aria-hidden`, so gate
  reasons reach sighted keyboard users but are never announced to screen
  readers — the accepted Track C P1 pattern; an `aria-describedby` hook on
  the primitive would close it for the whole band at once.

### Component checklist (delta)

- `UndoIcon` / `RedoIcon` glyph construction ✅ (family-true; P3 comment nit)
- History ToolGroup a11y (names, aria-disabled gating, focus tooltip) ✅
- History group honest gating (server `can_undo`/`can_redo`, lock reason) ✅
- Undo/redo chord grammar (mac/win, typing-target guard, ⌘Y unbound) ✅
- CreateStrip fit at 1280×800 🔴 — P2 above (CI screenshot to confirm mode of failure)
- Busy-state caption honesty 🟡 — P3 wrong-direction verb

### Resolution — fix pass (2026-07-17, follow-up commit)

- **P2 band width — fixed at the primitive.** History ships icon-only outright
  (Fusion precedent; ~90 px back) AND `ToolButton` gained a label TIER:
  `showLabel` renders its text only ≥1360px viewport (every `showLabel`
  surface is a full-width band, so the viewport query IS its container query;
  padding follows the tier). Arithmetic: labeled band ≈ 1315 px natural →
  fits ≥1360 with ~45 px margin; below the tier the label-shed band ≈ 580 px →
  categorical fit at 1280. e2e (`undo-redo.spec.ts` 1280×800 block) asserts
  Measure's right edge inside the frame + zero band scroll-overflow, and
  captures `undo-redo-band-laptop.png` for render confirmation in CI.
- **P3 busy caption — fixed.** `historyHold` ("undo" | "redo" | "rollback")
  threads the actual in-flight tree write; BOTH held buttons caption the true
  reason ("Undoing…" while an undo runs — never the partner's verb; "Moving
  the rollback bar…" during a bar move).
- **P3 icon geometry — sharpened, not re-captioned.** True squared elbow
  (`M5 9 H16 V17 H8` / mirror about x=12) replacing the `A4.5` arc — rhymes
  with Perpendicular/Mirror's L-bends as suggested; ink ≈ 38 grid-units,
  still mid-family. Comment now matches the ink.
- **P3 chord chips — platform-aware via shared helper.** `formatChord()`
  (`packages/design/src/chord.ts`, node-tested, exported for future chips):
  "Ctrl+Z" → "⌘Z", "Ctrl+Shift+Z" → "⇧⌘Z" on Apple platforms, authored
  notation elsewhere; single-letter chips pass through verbatim.
- **Code-review batch (same commit):** non-stale undo/redo failures now
  surface an HUD alert (`history-error`, import-error affordance) and the
  measure-disarm/selection-clear hygiene runs only AFTER a confirmed restore
  (version-changed discriminator); `COMMAND_LABEL` re-keyed
  `Record<OpenEditor["kind"], string>` (compiler holds the band lock); chord
  grammar layout-proofed (`event.code` fallback for non-Latin layouts, label
  wins on Latin remaps — vitest matrix extended); rollback-bar drag and
  history steps mutually excluded (guards both directions + bar disabled
  while a step restores).
- **Deferred as agreed:** the band-wide `aria-hidden` tooltip SR gap →
  BACKLOG (an `aria-describedby` hook on the ToolButton primitive).

---

## 2026-07-18 — Spot-check: angular + point-to-point dimension authoring — commit `981c42f`

Static/token + a11y/UX review (live stack unbootable in sandbox — Docker
registry 403 per CLAUDE.md; render-level checks flagged CI-deferred). Scope:
`VertexHandle` + `vertexHandleMm`/`vertexHandleRest` tokens, the staged
multi-pick flow (hint pill + gated backdrop) in `DrawingPage`, the action-driven
`DimensionAuthorMenu`, and the angular / point-to-point rendered annotations.

### PASS

- **`DimensionAuthorMenu`** (`apps/web/src/components/DimensionAuthorMenu.tsx`)
  — clean refactor edge-type→action-driven; same anvil card, hairline rules,
  brass `focus-visible`, `disabled` while busy, auto-focus first item, per-action
  `data-testid`. Voice consistent (`Angle` hint `pick 2nd edge` is honest about
  arming a second pick; `°` / `↔` hints match the existing Ø/R idiom). Empty
  action list returns null — no orphan menu. No inline hex.
- **Staged flow** (`DrawingPage.tsx`) — genuinely non-modal as claimed: the
  `fixed inset-0` backdrop renders ONLY for a menu state (`anchor && actions>0`),
  never while a second pick is pending, so the sheet stays live for the second
  pick. Cancel is real and reachable: Escape is handled first in the global
  keydown (before the typing-target/modifier guards) so it always resets to
  `IDLE`, and it is not swallowed by `VertexHandle`/`PickableEdge` (those
  preventDefault only Enter/Space). Hint pill is `role="status"` (announced),
  `pointer-events-none` (never blocks a pick), eyebrow styling on tokens
  (`border-brass/60 bg-anvil text-brass font-display text-2xs`), carries an
  explicit `Esc to cancel`. Microcopy matches the app's terse voice.
- **Angular + point-to-point annotations** (`dimensions.ts`) — reuse the shared
  drafting primitives (`placeLinearBetween` factored out for both edge-length and
  p2p; `arrowPoints`, `extension`/`dimension` weights, the paper halo, the
  obstacle/sheet flip). Degree stamp is tight `${n}°` (1 dp) — matches the
  resolved app-wide symbol-suffix convention and does NOT reintroduce the earlier
  `MeasureReadout` `m`→`M` SI collision (angular uses the `°` glyph, linear stays
  bare). `~` foreshorten flag prepended in `dimensionFlag` ink, identical to the
  linear treatment; angular's `<title>` and the "stamped value is model-true, the
  drawn sweep is apparent" honesty is preserved. Unplaceable cases (unmatched
  edge, parallel angular edges, coincident p2p points) return null and list
  honestly rather than mis-draw. Render-geometry correctness (arc sweep side,
  arrow tangents) is CI/e2e-deferred and owned by code-review/geometry-qa.

### Findings

- **P2 — `DrawingSheet` `VertexHandle` — focus is NOT distinct from hover
  (WCAG 2.4.7 regression vs. its sibling primitive).** The handle collapses
  `const active = hover || focus || selected` and renders all three identically
  (fill→`pickSelected`, stroke 0.6). The sibling `PickableEdge`/`EdgeShape` was
  *explicitly* fixed for exactly this (2026-07-17 pass): hover recolors, focus
  adds a distinct deep-blue RING (`drawing.pickFocusRingMm`) — a shape cue, not
  colour-only. The new handle didn't inherit that seam.
  *System fix:* give `VertexHandle` the same focus treatment as `EdgeShape`
  (a `pickFocusRingMm` ring around the square on `focus`), so keyboard focus
  reads differently from mouse hover. `docs/screenshots` CI-deferred.
- **P2 — `DrawingSheet` — vertex handles render PERSISTENTLY on every
  straight-edge endpoint, adding non-geometry marks + a tab stop per corner to
  the hero blueprint.** `DrawingPage` always passes `onPickEndpoint`, and
  `SheetView` draws a handle for every dimensionable straight edge's ends
  whenever it is set — there is no authoring-mode / hover gate. Consequences vs.
  mandate 3 ("chrome recedes; the model gets the pixels") and 3a (benchmark
  Fusion/Plasticity, where vertex snaps appear on hover/proximity, not as
  permanent stamps): (a) a dense multi-view drawing gains dozens of small squares
  that are not geometry; (b) every corner becomes a keyboard tab stop *in
  addition to* every edge — this compounds the already-filed "tab-stop-at-scale"
  P3 (BACKLOG, 2026-07-17) rather than respecting it. `PickableEdge` adds no
  at-rest mark (it decorates the existing geometry edge on hover only); the
  handle is the first primitive to add persistent chrome to the sheet.
  *System fix:* reveal endpoint handles contextually — on edge hover/focus, or
  behind a "point-to-point" authoring affordance — instead of stamping all
  corners at all times; keep them out of the tab order until revealed.
- **P3 — `packages/design/src/tokens.ts` — `vertexHandleRest` duplicates a hex
  literal and the comment mislabels it.** `vertexHandleRest: "#6E7A88"` restates
  the exact literal of `edgeHidden: "#6E7A88"` in the same `drawing` object
  instead of aliasing it — the "no hex duplicated" DRY rule applies inside the
  token source too. The comment calls it "the quiet gauge graphite," but `gauge`
  is `#9DAABA`; the value is `edgeHidden`. *System fix:* `vertexHandleRest:
  drawing.edgeHidden` (or a shared `graphiteMuted` constant) + correct the
  comment.

### Component checklist (delta)

- `DimensionAuthorMenu` (action-driven) ✅ — type-gated, keyboard-first, honest hints, AA
- `DrawingSheet` staged multi-pick flow ✅ — non-modal, `role=status` hint, Esc cancels
- `DrawingSheet` `VertexHandle` ✅ — distinct focus ring + contextual reveal (fixed 2026-07-18)
- `dimensions.ts` angular + point-to-point placement ✅ — shared primitives, tight `°`, `~` parity (render CI-deferred)
- `vertexHandle*` tokens ✅ — aliases `edgeHidden` via `graphiteMuted`, comment fixed (2026-07-18)

### Resolution — fix pass (2026-07-18)

Frontend-builder pass closing all three filed `VertexHandle` findings (and the
code-review 🟡 cross-boundary duplication) on commit `981c42f`:

- **P2 focus not distinct from hover** — `VertexHandle` no longer collapses
  `hover||focus||selected`. Focus now draws a distinct deep-blue RING around the
  square (`drawing.pickFocusRingMm`, opacity 0.5 — `data-testid=
  "drawing-vertex-focus-ring"`), the exact seam `EdgeShape` uses; hover/selected
  recolor the fill, focus adds the shape cue. Keyboard focus reads differently
  from mouse hover (WCAG 2.4.7).
- **P2 persistent handles / tab-stop-per-corner** — the drawn square + its tab
  stop now appear only when **revealed**: on the owning edge's hover/focus (a
  reveal keyed on the edge in `SheetView`), on the handle's own hover (mouse
  proximity), or when a point-to-point pick is armed (`endpointPickActive`, which
  reveals every handle so the second vertex is reachable on any edge). Until
  revealed the handle is `tabIndex=-1` + `aria-hidden` — out of tab order and off
  the a11y tree — so a dense multi-view sheet no longer carries dozens of
  non-geometry squares or a tab stop at every corner. The transparent hit target
  stays attached at all times, so the pick (and the forced e2e click) still fires
  the moment the vertex is approached; the staged point-to-point flow is
  unchanged.
- **P3 token dedup** — `vertexHandleRest` now aliases `edgeHidden` through a
  shared module-level `graphiteMuted` constant (no repeated `#6E7A88`); the
  misleading "gauge graphite" comment is corrected (gauge is `#9DAABA`).
- **Code-review 🟡 (cross-boundary duplication)** — deleted `projectModelPoint`,
  the `VIEW_AXES`/iso-frame table, and the vec3 helpers from `layout.ts` (a twin
  of the geometry service's view frames). `endpointHandlesForEdge` /
  `endpointProjected` now derive the model↔projected endpoint correspondence from
  the wire's `start_is_end_a` bool alone; the point-to-point pick is gated on
  `source_edge != null && start_is_end_a != null`, so a straight edge missing the
  correspondence (silhouette/ambiguous) offers no vertex pick.

Gates: `@loft/web` unit (669) + `@loft/design` (31) + both typechecks + eslint/
prettier on touched files green. Drawings e2e is behaviourally unchanged (the
authored dimension is identical — only the internal correspondence source moved
from re-projection to the wire bool) and runs in CI; founder before/after shots
CI-deferred (sandbox Docker-registry 403 per CLAUDE.md).

---

## 2026-07-18 — Assembly BOM panel + SOLVE/PARTS toggle (spot-check cf617c8) — PASS

Static + token + screenshot review of the BOM parts-list schedule
(`AssemblyBomPanel.tsx`), its inspector wrapper (`AssemblyInspectorPanel.tsx`,
new `SegmentedControl` SOLVE/PARTS toggle), and the `AssemblyPage` wiring.
Judged against `docs/screenshots/assembly-bom-desktop.png`. Correctness
(fetch/aggregation/states) is covered by `bom.test.ts` + `assembly-bom.spec.ts`
and out of scope here.

**Design-system adherence — PASS.** Zero inline hex; every class resolves to a
`packages/design` token (`brass`/`etch`/`gauge`/`mist`/`flag`/`hairline`/
`anvil` via `Panel`, `font-display`/`body`/`data`, `text-2xs`/`base`,
`duration-fast`). Composes `Panel`/`PanelSection` and the existing
`SegmentedControl` primitive; no restyled raw chrome. Right-aligned QTY/TOTAL in
the `font-data` tabular-nums DRO idiom and the brass TOTAL rule match the app's
number/accent language. The hand-rolled `KindBadge` is NOT a primitive bypass —
no `Badge` primitive exists in `@loft/design`, and the chip recipe
(`rounded-sm px-1 font-display text-2xs uppercase tracking-[…]`) is the same one
`AssemblyTreePanel` already hand-rolls, so it is consistent with app convention.

**A11y — PASS.** Real semantic `<table>` (thead/`<th scope="col">`/tbody/tfoot),
not divs. Toggle is keyboard-operable via `SegmentedControl` real `<button>`s
(`aria-pressed`, `aria-label="View"`, `focus-visible:outline … outline-brass`).
The `missing:true` line conveys state as literal text `(deleted)` — the `⚠` is
`aria-hidden`, so SR users get the word, not colour/icon-only. Error is
`role="alert"`, loading is `aria-live="polite"`. Contrast on `anvil`: `flag`
6.5:1, `gauge` 7.2:1, `brass` ≈7.6:1, `mist` 13.2:1 — all AA. Name column
`truncate min-w-0` + `shrink-0` badge holds at 1280×800 without overflow.

Two P3 system-level follow-ups (neither blocks; both are repair-the-primitive):

- **P3 — inspector table — no accessible name on the `<table>`.** The parts-list
  `<table>` is announced as an unnamed "table"; the enclosing `<aside>` carries
  `aria-label="Bill of materials"` but the table element itself does not.
  System fix: add `aria-labelledby` to the eyebrow or a `sr-only` `<caption>`
  (candidate for a `PanelSection`-provided caption seam so every schedule gets
  one). Ref: `AssemblyBomPanel.tsx:85`.
- **P3 — design system — extract a `Badge`/`Chip` primitive.** The token chip
  recipe is now hand-rolled in ≥2 places (`AssemblyTreePanel`, BOM `KindBadge`),
  each re-picking arbitrary `tracking-[…]` values (BOM alone mixes
  `0.12`/`0.14`/`0.16em`). Per DRY "extract on the second real use," promote a
  `Badge` primitive to `packages/design` and let both compose it; fold the
  arbitrary tracking literals into a tracking scale token while there.

Verdict: ship as-is; queue the two P3s for the design-system backlog. No P1/P2.

---

## 2026-07-19 — Sheet-metal flat-pattern drawing UI (spot-check, commit 645f236)

**Scope.** The new flat-pattern surface: dashed-blue `bend` fold lines
(`drawing.bend` token), the columnar `BendTable` (BEND/ANGLE/RADIUS/DIR/ALLOW),
the Views-panel Cut-edge/Fold-line legend, the "Flat pattern" command-band
action (shortcut F), and the `flat_pattern_not_sheet_metal` inline error.
Source-audited against founder shots `docs/screenshots/sheet-metal-flat-pattern-
{l,u}-{1440,1280}.png`; contrast recomputed; DOM vs server composer
cross-referenced. Files: `apps/web/src/components/DrawingSheet.tsx`,
`apps/web/src/routes/DrawingPage.tsx` (`ViewsPanel`),
`apps/web/src/components/DrawingCommandBand.tsx`, `packages/design/src/tokens.ts`,
`services/geometry/src/geometry/drawings/compose.py`.

### Executive verdict

**Ship it.** The on-screen surface meets the tool-grade bar: the fold line reads
as a distinct dashed-blue phantom line (correct SolidWorks/Fusion flat-pattern
vernacular, clearly not the blueprint-blue pick accent), the bend table is a
dense quiet columnar instrument (not a card), every chrome element is wired to
real state, and the token discipline is clean — `drawing.bend = #2F6FEB` is a
genuine single-source token whose hex + weight + dash exactly match the server
composer's `_EDGE_BEND`/`_BEND_W`/`_BEND_DASH`, so the on-screen fold line is
byte-identical to the exported one. Contrast claims verified. The findings below
are one real P2 (export/screen bend-table divergence) and polish nits; none
block the founder's morning review.

### Findings

- **P2 — bend table — the three outputs of ONE sheet disagree; PDF/DXF (the shop
  deliverables) don't match the screen. ✅ RESOLVED 2026-07-19
  (`services/geometry` — kernel-architect).** The server SVG/PDF/DXF serializers
  now render the bend table in the SAME 5-column columnar layout, precision, and
  labels as the on-screen DOM `BendTable`: captions BEND/ANGLE/RADIUS/DIR/ALLOW mm,
  cells `bend-1 · 90.0° · R3.00 · UP · 6.09` (angle 1dp + °, radius 2dp `R2.00`,
  allowance bare 2dp — the DOM's canonical format). One shared `_bend_row_cells`
  helper + `_BEND_COL_DX`/`_BEND_TABLE_CAPTIONS` constants (comment-anchored to the
  DrawingSheet.tsx canonical spec) feed all three server serializers, so they are
  pure layout passes and can't re-format independently. DRY-locked by a new
  cross-serializer consistency test (`test_bend_table_text_consistent_across_
  serializers`) asserting SVG/DXF emit identical ordered cells + PDF contains them;
  byte goldens regenerated to the unified format. **Follow-up (deeper DRY, spans
  frontend — BACKLOG SM-fmt-1):** pre-format display-ready cells INTO
  `ComposedBendTable` server-side so the DOM `BendTable` and all serializers become
  a single layout pass over shared strings (kills the Python/TS format duplication
  entirely). Not done here to stay in the `services/geometry` territory.
  Original finding below for context. — The on-screen `BendTable`
  (`DrawingSheet.tsx:1011`) renders a proper 5-column grid with per-column
  captions (BEND/ANGLE/RADIUS/DIR/ALLOW mm), radius at 2dp (`R2.00`), allowance
  bare at 2dp (`3.14`). **Export SVG** serializes this DOM `<svg>` (WYSIWYG, so
  it matches). But **Export PDF** and **Export DXF** are server-composed
  (`compose.py` `_emit_bend_table`/`_pdf_bend_table`/`_dxf_bend_table` via
  `_bend_row_text`), which emits a *single "BEND TABLE" heading* + *run-together
  single-line rows* `B1  90.0°  R2.000  UP  BA3.140` — radius 3dp, allowance
  BA-prefixed 3dp, no column captions. So the same drawing's SVG vs PDF/DXF bend
  tables differ in **layout, precision, and labels**, and the shop deliverable
  doesn't look like the screen. This breaks WYSIWYG on the signature sheet-metal
  surface. Root cause: the bend table is NOT "one composed model, N renderers" —
  `ComposedBendTable.rows` carries numbers and each renderer re-formats + re-lays
  out independently (a WET/DRY defect: two column/precision layouts that have
  already diverged). System fix: make the server composer render the SAME
  columnar layout + number formatting as the DOM `BendTable` (or lift the column
  x-offsets + `toFixed`/prefix rules into the shared composed model so both
  renderers consume them). Screenshot ref: on-screen vs a PDF/DXF export of the
  same flat pattern. Screen + SVG are correct; PDF/DXF are the fix targets.

- **P3 — bend-table values have no text-accessible equivalent (SVG is
  `role="img"`). ✅ RESOLVED 2026-07-19 (frontend-builder).** New DOM
  `BendSchedulePanel` (`DrawingPage.tsx`) renders the per-bend values as a real
  `<table>` with `scope="col"` headers (BEND/ANGLE/RADIUS/DIR/ALLOW mm) + an
  `sr-only` caption, so AT reads each cell's meaning and a keyboard/non-pointer
  user reaches the fold data the `role="img"` sheet hides. Keyed POSITIONALLY to
  the flat view's `edge_role="bend"` fold lines (the i-th `bend-schedule-row` ↔
  the i-th bend edge via the same `data-bend-index` contract — never a `bend_id`
  join), values formatted to match the printed sheet (90.0° / R3.00 / UP / 6.09).
  Testids `bend-schedule-panel`/`bend-schedule-row`; existing SVG hooks untouched.
  E2e (L-bracket 1 row, U-channel 2 rows) asserts the panel; founder shots
  refreshed. Original finding below. — The root sheet `<svg>` is `role="img"` with a single summary
  `aria-label` (`DrawingSheet.tsx:1120-1124`), so AT treats the whole sheet as
  one opaque image and never descends into the `BendTable`'s `aria-label="Bend
  table, N bends"` or its per-row text — those hooks serve tests, not screen
  readers. The `ViewsPanel` exposes only the bend *count* in the DOM; the
  per-bend angle/radius/direction/allowance are unreachable to a screen-reader or
  non-pointer user. (Same structural gap the dimension glyphs have, but there the
  `DimensionsPanel` mirrors every value in the DOM — bends have no such panel.)
  System fix: a DOM bend-schedule panel mirroring `DimensionsPanel` (also gives
  keyboard users the fold data), reusing the same `data-bend-index` keying.

- **P3 — `ViewsPanel` fold-line legend swatch dash/ink don't mirror the sheet.**
  ✅ RESOLVED 2026-07-19 (frontend-builder). The fold-line legend swatch now
  drives its `strokeDasharray` from `drawing.bendDashMm`/`bendGapMm` (the SAME
  tokens the real fold stroke uses), and the hidden-edge swatch from
  `hiddenDashMm`/`hiddenGapMm` — the legend can no longer drift from the strokes
  it documents. Original finding below. — The legend fold swatch (`DrawingPage.tsx:948-957`) uses `drawing.bend` (good —
  true token, 3.88:1 on `anvil`, passes 1.4.11) but hardcodes
  `strokeDasharray="4 2"`, whereas the actual fold line is `3 1.6`
  (`bendDashMm`/`bendGapMm`); and the Cut-edge/Visible/Hidden swatches use
  `currentColor` chrome inks (`text-mist`/`text-gauge`) rather than the sheet's
  graphite tokens (defensible — graphite is invisible on the dark panel — but it
  makes the legend a loose approximation, not a true key). Low-stakes truthfulness
  nit. System fix: drive the swatch dash from `drawing.bendDashMm`/`bendGapMm`
  (a `<DashSwatch strokeDasharray>` derived from the tokens) so the key can't
  drift from the stroke it documents.

- **P3 — `BendTable` column x-offsets are hardcoded magic numbers coupled to a
  92mm block.** ✅ RESOLVED 2026-07-19 (frontend-builder, client-side de-magic).
  The `BendTable` columns now derive from the server-given `table.width`
  (`x + width * fraction`), the fractions named as a design token
  `drawing.bendTableColumnFractions` (the `_BEND_COL_DX / _BEND_TABLE_W` ratio),
  and `headerH`/`rowH` read from new `drawing.bendTableHeaderMm`/`bendTableRowMm`
  tokens (matching `_BEND_TABLE_HEADER_H`/`_ROW_H`) — no absolute-mm magic left in
  the renderer. The DEEPER cross-boundary share (server pre-formats display cells
  into `ComposedBendTable`) stays filed as BACKLOG SM-fmt-1 (changes the wire
  schema + backend), out of scope here. Original finding below. — `col.bend/angle/radius/dir/allow` (`DrawingSheet.tsx:1017-1023`)
  are literal `x+3/26/43/62/77`, commented "Sized for the 92 mm block," but the
  block `width` is read from the server (`_BEND_TABLE_W`). `headerH`/`rowH`
  (7/6) are also re-declared here, duplicating `_BEND_TABLE_HEADER_H`/`_ROW_H`.
  If the server ever changes the block width or row metrics, the DOM columns
  silently misalign / overflow. Not a live defect (values agree today). System
  fix: derive columns as fractions of `table.width` and carry `headerH`/`rowH`
  in the composed model so the single source drives both renderers.

### Verified PASS (no action)

- **Token single-source (P1 lens):** `drawing.bend #2F6FEB` == server
  `_EDGE_BEND`; `bendWeightMm 0.4` == `_BEND_W`; `bendDashMm/bendGapMm "3 1.6"`
  == `_BEND_DASH`. Fold-line stroke, hidden/visible strokes, dimension inks,
  title-block inks all read from `@loft/design`; no raw hex in the components.
- **Contrast (builder's claims confirmed):** bend stroke #2F6FEB on paper
  #ECEFF2 = **3.96:1** (≥3:1, WCAG 1.4.11 graphical); caption `drawing.label`
  #48525E = **6.89:1**; value `drawing.dimensionText` #1B222B ≈ **13:1**. The
  sheet is theme-independent (always the paper inversion — no light theme
  exists; whole product is all-dark), so there is no dark-theme regression to
  check on the sheet content. Fold-line legend swatch on `anvil` = 3.88:1, passes.
- **Focus / disabled explainability:** the F "Flat pattern" `ToolButton` uses
  `aria-disabled` (not native `disabled`), so it still hovers/focuses and its
  reason `caption` reaches both mouse and keyboard (and SR via
  `aria-describedby`) — no `pointer-events-none` tooltip trap. Brass
  `focus-visible` outline. F is keyboard-reachable via the global handler AND the
  focusable button; Escape clears authoring, doesn't destroy layout. Pickable
  edges/vertex handles keep custom SVG focus rings (`pickFocusRingMm`) distinct
  from hover recolor (WCAG 2.4.7).
- **Responsive 1280×800:** the sheet is one `preserveAspectRatio="xMidYMid meet"`
  SVG that scales uniformly, so the table anchor (top-left) / title block
  (bottom-right) placement is width-independent — no DOM overflow between 1440
  and 1280. `showLabel` command-band tools shed labels below 1360px, so the band
  doesn't clip at the floor. (Table-vs-blank overlap, if any, is a server mm
  placement concern, not a DOM responsive bug — not observed in the founder shots.)
- **Missing states:** loading ("Projecting…"/"Unfolding…" captions +
  `drawing-projecting`), empty (`SetupHint` naming the flat-pattern path), error
  (`FailedView` renders `flat_pattern_not_sheet_metal` as forward-looking
  guidance — "Add a base flange and an edge flange…" — never a silent blank).
- **Test hooks intact:** `drawing-bend-table`, `drawing-bend-row`,
  `data-bend-index`, `drawing-view-error` (+ `data-error-code`),
  `drawing-flat-pattern`, `drawing-bend-count`, `drawing-edge-role="bend"` all
  present and mirror the server SVG hooks.

Running checklist: Flat-pattern sheet (screen) ✅ · Bend fold-line token ✅ ·
Views legend ✅ (dash tokenized 2026-07-19) · Flat-pattern action + F shortcut ✅ ·
flat_pattern_not_sheet_metal error ✅ · **Bend-table export fidelity (PDF/DXF) ✅
(P2 fixed 2026-07-19)** · Bend-table SR access ✅ (P3 BendSchedulePanel 2026-07-19) ·
BendTable column de-magic ✅ (P3 2026-07-19). All three P3 nits from this pass closed.

---

## 2026-07-19 — Spot-check: sheet-metal HemEditor + CornerReliefEditor — commit `0c10265`

**Scope.** The two new sheet-metal authoring editors, judged as tool-grade
modeling chrome against the shipped `BaseFlangeEditor`/`EdgeFlangeEditor` (the
bar) and vs. how SolidWorks/Fusion author these. Read-only: source of both
editors + the `sheetMetal.ts` view logic + the `@loft/design` primitives they
compose + `CreateStrip` gating + the error-envelope path, plus founder shots
`sheet-metal-hem-{body,flat,edit}-*` and `sheet-metal-corner-relief-{body,flat}-1440`.

### Executive verdict — SHIP IT

Both editors clear the tool-grade bar. They compose **only** `@loft/design`
primitives (Panel / NumberField / SelectField / Checkbox / PanelActionCell) —
zero restyled raw inputs, zero hex literals, the "180° (closed)" readout and
the live notch preview both token-inked (`text-mist` / `text-gauge` /
`font-data`). The `HemEditor` chrome is **byte-consistent** with
`EdgeFlangeEditor` — identical title-block strip, eyebrow, single-select
edge-pick block (reuses the shared overlay + store), brass length handle,
inherited radius/K overrides revealed per-toggle, 2-col Cancel/Create action
grid, flag-inked `role="alert"` error tail — it reads as the edge flange
minus the fold-angle field, exactly as intended. Founder shot
`sheet-metal-hem-edit-1280` confirms it: the brass/white edge diamonds, the
"1 edge picked" readout, the "180° (closed)" caption, the two override rows
all land clean. The corner-relief feature-select is an **acceptable v1** (see
P2 below for the one real follow-up). A11y floor met in both. Findings are
nits + one fast-follow; nothing blocks.

### Findings

- **P2 — CornerReliefEditor — the Bend A / Bend B selects are "blind": no
  viewport feedback ties a dropdown option to a physical flange/corner.**
  Feature-select is a legitimate tool-grade v1 — SolidWorks/Fusion do let you
  pick the corner/edges in the 3D view, but they *also* expose corner
  treatments off feature lists, and two ruled selects captioned "The two edge
  flanges whose bends meet at the corner to relieve" are discoverable and —
  critically — **fully keyboard-reachable, which a viewport pick is not yet**.
  So the deferred direct-pick call is VALIDATED. The gap that bites *now*: with
  3+ edge flanges the user must guess which two named "Edge flange3 / Edge
  flange4" meet at the corner they want, with nothing highlighting the chosen
  bend in the scene. The full viewport bend-face pick is the right long-term
  fix (roadmap-tracked) — but the **cheap interim that closes most of the gap
  without new pick infrastructure** is to flash/highlight the selected flange's
  bend in the viewport when Bend A/B changes, reusing machinery that already
  exists (selecting the feature already tints the body brass; the edge-pick
  overlay already highlights edges). Suggested system-level fix: on
  `bendAId`/`bendBId` change, drive the existing feature/edge highlight for that
  flange. Ref: no editor-open corner-relief shot exists yet (see last P3).
- **P3 — CornerReliefEditor — autofocus lands on "Relief ratio", not "Bend A".**
  In create mode the two bends are seeded to the first two edge flanges in tree
  order, which are frequently *not* the corner the user means; the first thing
  a user typically retargets is the bend selection, yet keyboard focus starts
  two fields below it (must shift-tab up). The hem/edge-flange autofocus-the-
  handle idiom doesn't transfer cleanly here because the "handle" (ratio) has a
  safe default while the *references* are the risky guess. Suggested fix:
  autofocus Bend A. Ref: `CornerReliefEditor.tsx:143` (`autoFocus` on ratio).
- **P3 — CornerReliefEditor — no placeholder option and no guard for an
  unresolvable stored bend ref.** `edgeFlangeOptions` filters out rolled-back
  flanges, so in *edit* mode a `bendAId`/`bendBId` pointing at a since-rolled-
  back/deleted flange yields a `value` absent from `options`; the native
  `<select>` then displays its FIRST option while form state holds the stale id
  → the panel silently shows the *wrong* flange. The server catches the write
  as `reference_unresolved` so no wrong model ships, but the editor is
  misleading in the interim. Rare, but a placeholder "— select bend —" option
  (or a resolved-ref guard) would make the mismatch legible. Ref:
  `CornerReliefEditor.tsx:91,115-133`.
- **P3 — CornerReliefEditor — the live notch preview updates silently (no
  `aria-live`).** `corner-relief-size-preview` recomputes on every ratio
  keystroke but is a plain `<p>`, whereas the sibling readout pattern
  (`hem-pick-count` / `edge-flange-pick-count`) carries `aria-live="polite"`. A
  screen-reader user typing the ratio never hears the resolved notch mm.
  Suggested fix: add `aria-live="polite"` to the preview for parity. Ref:
  `CornerReliefEditor.tsx:150-157`.
- **P3 — corner-relief tool gate copy over-promises adjacency.**
  `canAuthorCornerRelief` arms the tool at ≥2 edge flanges (`sheetMetal.ts:545`),
  but the enabled aria-label promises "two edge flanges that **meet at a
  corner**". Two flanges on parallel/non-touching edges arm the tool; the kernel
  then rejects the pair as `corner_relief_failed`. The gate is honest about the
  *count*; the copy describes a stricter *adjacency* condition the gate doesn't
  check. Acceptable (kernel validates, typed error surfaces as guided text —
  see PASS), purely cosmetic. Ref: `CreateStrip.tsx:612-617`.
- **P3 — evidence gap (process, not product).** The hem set includes an
  open-editor shot (`sheet-metal-hem-edit-1280`); corner relief has only
  `body`/`flat`. The design-mandate surface should ship an **editor-open** shot
  of the `CornerReliefEditor` panel (the two selects + ratio + notch preview)
  too. Refresh with `UPDATE_SCREENSHOTS=1`.

### Verified PASS (no action)

- **Design-system adherence** — both editors compose only `@loft/design`
  primitives; no restyled raw `<input>`/`<select>`; no hex literals; the
  "180° (closed)" fold readout and the `≈ … mm (ratio × gauge)` notch preview
  are token-inked, not hardcoded. `HemEditor` chrome is byte-identical to
  `EdgeFlangeEditor` (strip, eyebrow, pick block, override-toggle reveal,
  action grid, error tail).
- **A11y floor (light + dark)** — on `bg-anvil`: mist 13.2:1, gauge 7.2:1,
  flag 6.5:1 all clear AA (incl. the 10px `text-2xs` gauge notch preview +
  checkbox descriptions). Visible brass focus on the pick-clear button, both
  `SelectField`s (`focus-within` ring via the primitive), checkboxes, and the
  action cells. The "180°" readout is real DOM text (exposed to AT, **not**
  `aria-hidden`/decorative). Pick errors + the same-bend error carry
  `role="alert"`; `hem-pick-count` carries `aria-live`. `SelectField` gives
  proper `label htmlFor`, `aria-invalid` + `aria-describedby` on error.
- **Disabled-affordance honesty** — the disabled submit `PanelActionCell` uses
  `disabled:pointer-events-none` but carries **no** tooltip, so it is not a
  pointer-events tooltip trap; the reason is reachable by mouse and keyboard via
  the always-visible inline field errors / pick guidance, and the in-command
  band's OK cell *does* self-explain (`caption="Finish the form"` when the
  form's submit gate is false — `CreateStrip.tsx:322`).
- **Consistency + states** — hem mirrors edge-flange interaction language
  exactly (single-select pick, Enter commits / Escape cancels, per-toggle
  override reveal). Disabled corner-relief reason "Needs two edge flanges" is
  honest about the gate; the same-bend inline error guides
  ("Pick two different edge flanges…"). Typed `corner_relief_failed` /
  `reference_unresolved` surface as the server's **human** message via
  `envelopeMessage` (not raw codes) in the flag-inked `role="alert"` panel —
  guided inline state, never a silent wrong model.
- **Test hooks** — `hem-*` (editor, pick-clear, pick-count, pick-error, length,
  fold-readout, override-radius/k, bend-radius, k-factor, cancel, submit, error)
  and `corner-relief-*` (editor, bend-a, bend-b, ratio, size-preview,
  override-size, size, cancel, submit, error) are complete and mirror the
  `edge-flange-*` conventions; `SelectField` forwards `data-testid` onto the
  native `<select>`.

Running checklist: `HemEditor` ✅ (edge-flange twin, byte-consistent) ·
`CornerReliefEditor` ✅ ship — **P2 viewport-highlight-on-select fast-follow**
+ 3× P3 (autofocus Bend A · unresolvable-ref placeholder · notch-preview
`aria-live`) + P3 gate copy + P3 editor-open screenshot · SHEET METAL group
Hem/Corner-relief buttons ✅ (honest gating, engraved shortcuts) · full
viewport corner/bend pick = validated deferred follow-up (roadmap).

---

## 2026-07-23 — SPOT-CHECK: assembly export + clash inspector (`49f01ba`) · section-view author (`06fc019`)

**Method.** Audited the **committed** source (working tree held by concurrent
agents) + the founder shots `assembly-{export,clash-found,clash-empty}-*`,
`assembly-clash-found-laptop` (1280), `drawings-section-{before,author,after}-*`
(1280 + 1440). Cross-referenced `packages/design/tokens.ts` (`assembly.clash`
/`clashTint`, `drawing.hatch`), `FloatingPanel` (overflow), `ToolButton`
(`active`→`aria-pressed`).

### Executive verdict — both surfaces are TOOL-GRADE. Ship.

Both new surfaces read as the app's existing quiet precision instruments, not
bolted-on. **Design-system adherence is clean:** zero raw hex in either
component; both alarm/hatch inks come from named shared tokens
(`assembly.clash`=`color.flag`, `clashTint` #F2C9C9, `drawing.hatch` #7A8695)
consumed by both renderers — the clash flag is one language across DOM tree
badge + WebGL edge/tint + balloon, and the on-screen hatch reads from the same
token the server serializer emits. Composed entirely from `Panel`/
`PanelSection`/`SegmentedControl`/`ToolButton`/`ToolGroup` primitives. **A11y
floor holds:** `text-flag` (6.5:1 on anvil) clears AA even at `text-2xs`; hatch
4.0:1 clears the 3:1 graphical-object floor and is `aria-hidden` (decorative
fill, meaning carried by the "SECTION A-A" caption); async states carry
`aria-live`/`role="alert"`; visible brass focus on every control; `active`→
`aria-pressed` on the plane picker; `prefers-reduced-motion` snaps the
snap-on-solve lerp. **Every chrome element is functional** (rule 3c): the
clash schedule, export strip, plane picker, and Near/Far toggle all drive real
state — no decorative readouts. **Empty/error/loading complete:** clash has
distinct idle ("Run Check interference…"), busy ("Scanning for overlaps…"),
empty ("No interferences found…"), and error branches; section has
loading-datums, the client-side not-principal precondition alert (before
persist), and typed server `failed-view` guidance (`section_plane_not_*`).
**Responsive:** FloatingPanel caps height + `overflow-y-auto`, so the clash
schedule and BOM scroll rather than overflow; laptop 1280 shot shows the
inspector + schedule non-overflowing; the section author is `w-editor
max-w-full` and clears the 1280 sheet.

### Findings (all polish — none block)

- **P3 — assembly clash schedule — `AssemblyClashPanel.tsx` — pair rows are
  static, don't navigate.** A machinist reading an interference report expects
  to click a pair and have the viewport isolate/frame it; today all clashing
  bodies flush red at once and rows are read-only. Fine for the shipped 2-body
  case, but with many pairs you can't map a schedule row to its bodies. Not a
  rule-3c defect (rows reflect real state). *System fix:* make a clash row a
  selectable control that sets a "focused clash pair" (frame + solo-tint that
  pair), mirroring the tree's `onSelectInstance` idiom. Screenshot ref:
  `assembly-clash-found-desktop.png`.
- **P3 — clash + mate rows — `AssemblyClashPanel.tsx` / `AssemblyTreePanel.tsx`
  — the `①{n} ✕ ②{n}` glyph double-encodes.** Renders literally as "①1 ✕ ②2":
  the circled-digit `①`/`②` is used as an A/B slot marker, then the real
  balloon number follows, so when slot and balloon coincide it reads as a
  duplicated "①1". First-time-legible only once you know `①`=slot-A. It is
  *consistent* with the existing mate-row idiom (so not new), but the fix is
  system-level: extract a shared balloon token/`<Balloon>` element (the same
  drawn circle the tree/viewport use) instead of the unicode circled-digit as a
  slot prefix. Screenshot ref: `assembly-clash-found-desktop.png`.
- **P3 — assembly clash — `AssemblyClashPanel.tsx` comment vs. render.** The
  panel doc says "flag red is spent on the count + each row's balloons," but
  the `Interference · N` count sits in the `PanelSection` eyebrow (gauge gray)
  — only the row balloons are red. Cosmetic/comment drift; either redden the
  count or fix the comment. Screenshot ref: `assembly-clash-found-desktop.png`.
- **P3 — assembly export strip — `AssemblyInspectorPanel.tsx` — strip scrolls
  with a long schedule.** The always-present EXPORT strip sits below the view
  inside the FloatingPanel scroll area, so a long clash/BOM list scrolls the
  strip out of the fold. Acceptable (it's reachable), but a sticky-footer strip
  would keep "the whole solved assembly writes to STEP/STL" always in reach.

Running checklist: `AssemblyClashPanel` ✅ · `AssemblyInspectorPanel`
(Solve/Parts/Clash toggle + export strip) ✅ · `AssemblyCommandBand`
(Check-interference, honest `I` gating + "Scanning…" busy caption) ✅ ·
`AssemblyTreePanel` CLASH badge ✅ · `AssemblyScene`/`InstanceMesh` clash
edge+tint (shared token, reduced-motion snap) ✅ · `SectionAuthorPanel`
(plane picker reuses sketch vocabulary, Near/Far, pre-checked precondition,
`aria-pressed`) ✅ · `DrawingCommandBand` Section action ✅ · `DrawingSheet`
`SectionHatch` (token-matched ink, `aria-hidden`, typed failed-view guidance)
✅. 4× P3 polish, zero blockers.

## 2026-07-24 — HARD AUDIT (founder-directed): "a competitor of Fusion 360 and Plasticity"

**Trigger (founder, verbatim):** "Also audit the ui hard. It should be a
competitor of fusion 360 and plasticity." This is design-mandate 3a applied
to the WHOLE product: tool-grade viewport, judged side-by-side, every chrome
element functional, "premium dashboard" explicitly not the bar.

**Method.** Real native stack on isolated ports (gateway :8030, documents
:8031, geometry :8032, Vite :5193), driven in real Chromium at 1440×900 and
1280×800. Every surface exercised: sign-in, three registers, part workspace
(empty / bracket / deep 16-feature tree / broken rebuild), sketch mode
(plane pick, rubber band, snap, dimension input), feature editors, measure,
assembly (2-instance mate flow, 8-instance dense, 6-instance clash stress),
drawings (setup, sheet). 45 evidence shots in `docs/screenshots/audit-ui/`
(01–40 from the first pass of this audit, 41–45 regenerated/extended this
relaunch). Source cross-referenced for every finding; no app code touched.

### Executive verdict

**The 2026-07-16 P0s are genuinely fixed and it shows.** The grid reads to
the horizon, bodies carry the studio matcap ("machined aluminum"), the
ViewCube + view rail are persistent, panels float over a full-bleed canvas,
and the instrument chrome is honest — every tile on the part inspector
(mass, bbox, topology, status, export) is live data; the old decorative
badges are gone. The part workspace at rest (`11-bracket-default-1440.png`)
now reads Plasticity-adjacent at a glance, and the failure surfaces (broken
rebuild `24`, clash inspector `43`) are *ahead* of the hobby-tool bar —
typed errors, per-pair interference volumes, honest SKIP chips.

**What still breaks the peer-tool claim is one regression and a depth gap.**
The regression: the command band has outgrown its width-tier arithmetic and
silently hides whole tool groups (SHEET METAL, INSPECT/MEASURE) at 1440 and
even 1600 wide — and hovering a hidden tool horizontally scrolls the entire
app. A Fusion user at 1440×900 would conclude the tools don't exist. The
depth gap: no live preview while editing, no feature-localized selection
(everything tints whole-body clay), no context menu, pre-pick affordances
rendered as blankets of DOM squares. Fusion/Plasticity feel comes from the
scene *responding* — ours still mostly responds after commit.

### Findings (P0 breaks the peer-tool claim · P1 clearly behind · P2 parity polish · P3 nit)

- **P0 — command band — labeled tier overflows the frame at 1440–1600;
  hidden groups + root horizontal scroll.** At 1440 the band cuts off at
  COMBINE (`11-bracket-default-1440.png`, right edge); at 1600 SHEET METAL
  is half-clipped and INSPECT is gone (`29-band-1600.png`); hovering the
  off-frame MEASURE scrolls the whole app sideways leaving half the frame
  black (`19-bracket-measure-armed-1440.png`). At 1280 the icon-only tier
  fits perfectly (`25-bracket-default-1280.png`) — the bug lives only in the
  labeled tier. Root cause: `ToolButton.tsx:51-57` sheds labels below 1360px
  on arithmetic ("labeled band ≈ 1315px natural") written before the SHEET
  METAL + INSPECT groups landed; `TopToolbar.tsx` is `overflow-visible` flex
  with no overflow management. **Fix (primitive):** recompute the label tier
  (labels only ≥ ~1800px, or shed per-group), and clamp the band so it can
  NEVER widen the root (`overflow-x-clip` + assert no horizontal scroll).
  Backlog-sized; add a Playwright guard: `top-toolbar` scrollWidth ==
  clientWidth at 1280/1440/1600 and INSPECT visible at all three.
- **P1 — tool tooltips (incl. disabled reasons) occluded by floating
  panels.** The gate-reason tooltip work (aria-describedby, hover+focus on
  `aria-disabled`) is right, but visually the tooltip loses to the feature
  tree: `TopToolbar` `relative z-10` creates a stacking context, so its
  tooltips' `z-30` can never beat the panels' `z-30` outside it — the CREATE
  group's tooltips render *behind* the tree panel
  (`27-disabled-tooltip-occlusion-1440.png`; the orphan "Import" sliver
  visible across `21`–`24`). Screen readers get the reason; sighted mice
  don't. **Fix (primitive):** lift the band's stacking context above panels
  (band z-40) or portal ToolButton tooltips to the root.
- **P1 — selection language: whole-body clay swap, never feature-localized.**
  Selecting ANY feature or body replaces the studio matcap with a flat warm
  tan across the entire body (`14`, `15`, `18`); selecting `Sketch1` gives
  no sketch-specific feedback at all (same whole-body tint). The tint reads
  as a material change (clay render), kills the machined look, and persists
  in every later glance; tree and geometry still never point at each other
  at feature granularity. Fusion tints the *feature's faces*; Plasticity
  outlines. **Fix (primitive, `ModelMesh` + face maps):** keep matcap
  luminance and mark selection with brass edge emphasis + a subtle overlay
  on the selected feature's faces only; distinct body-select vs
  feature-select states.
- **P1 — feature editors still commit blind (no live preview).** Open since
  2026-07-16: distance 30 typed in Edit Extrude, viewport still shows the
  12 mm body, no ghost (`20-bracket-extrude-editing-no-preview-1440.png`).
  Extrude ghost first, then datum/fillet. This is the single biggest
  "responds while you work" gap vs both benchmarks.
- **P1 — right-click is dead everywhere.** No context menu on body, canvas,
  tree, or anywhere (`17-bracket-rightclick-1440.png`; `grep onContextMenu
  apps/web/src` → zero hits). Fusion's marking menu is its speed backbone.
  **Fix:** one small token-styled viewport context menu (fit, view snaps,
  sketch-on-face, measure, suppress/delete selected) + tree-row menu.
- **P2 — pre-pick affordances are DOM-square blankets, not topology
  highlights.** Mate face-pick scatters white squares over every candidate
  face (`34-assembly-mate-hud-1440.png`); measure does the same for every
  vertex (`19`). Functional and test-friendly, but it reads as debug
  markers — the benchmarks highlight the face/edge *under the cursor*.
  **Fix:** raycast hover highlight on real topology; keep the DOM nodes as
  invisible test hooks (`measure-vertex-N` stays).
- **P2 — body hover is imperceptible.** Hover only brightens edges
  (`ModelMesh.tsx:82` "hover only brightens the edges") — `12` vs `11` are
  pixel-identical at a glance. Pre-selection glow should be unmistakable.
- **P2 — orbit/pan/zoom have zero discoverability.** ViewCube + view rail
  are good (`18-bracket-top-view-1440.png` — snaps work, tooltips name
  them), but nothing anywhere teaches drag/pan/zoom bindings — no status
  legend (Fusion), no first-run hint. A quiet mouse-legend chip near the
  view rail would close it.
- **P2 — registers (parts/assemblies/drawings homes) are consistent but
  templated.** Plain centered web tables on a faint grid
  (`02-parts-home-1440.png`) — none of the machine-shop identity the
  workspaces carry (frontend-design calibration: "generic but consistent"
  is still a finding). Low priority vs the modeling surfaces, but a
  thumbnail strip or engraved register treatment would make the first
  screen after sign-in feel like the same product.
  **✅ FIXED 2026-07-25 (frontend-builder).** Diagnosed as an information
  defect before a visual one: the two widest columns were CREATED and UPDATED
  rendering the *same* ISO date, so the surface answered nothing. It now
  answers what a returning engineer scans for — **LAST WORKED** (relative age
  of the last edit; `updated_at` is bumped by every tree write) which doubles
  as the empty-stub flag ("Not started" = no edit since it was named), and
  **UNITS** from `length_unit`, dropped entirely on drawings rather than ruled
  blank. Deliberately NOT invented: "has a body / has drawings / is broken" are
  not on the wire for a list. Form extends the existing language — sheet number
  moved into a scribed carbide gutter carrying the addressed row's brass
  scribe, the create control is the register's NEXT LINE (next sheet number,
  the `N` chord finally shown), unfiled ruled lines run to the frame edge (the
  centered-card-in-a-void read is gone). All three homes are now ONE
  `DocumentRegister` (closes the 2026-07-16 near-dup note too). Shots
  `parts-home-{empty,desktop,laptop}.png`.
- **P2 — assembly framing/read is the flattest of the three scenes.** Same
  matcap, but top-down default fit + small-in-frame parts + balloon squares
  (`41-assembly-dense-8-1440.png`) read flatter than the part studio; the
  2-instance mate flow frames both parts but low in-frame (`34`). A
  slightly lower default orbit + fit padding would let the studio shading
  actually model the faces.
- **P3 — solve readout shows a bare "—" in a fresh sketch**
  (`44-sketch-mode-1280.png` SOLVE panel) — an em-dash with no meaning
  attached; say "No constraints yet."
- **P3 — top/ortho views show rectangular shading bands** (ground-shadow
  plane seams visible from directly above, `18`); clamp the shadow plane or
  fade it in ortho top.
- **P3 — sketch-mode 1280 icon strip** (`44`): fits and works; MODIFY's 9
  unlabeled glyphs are scannable only via tooltips — acceptable, revisit
  with the band-tier fix.

### Side-by-side verdicts (would a Fusion/Plasticity user read it as a peer at a glance?)

| Surface | Verdict | Top visual reason where not |
| --- | --- | --- |
| Part workspace (rest) | **Yes** — `11` vs Plasticity holds up | band-hidden tool groups at 1440 (P0) |
| Part workspace (interacting) | **Not yet** | no preview / clay selection / dead right-click |
| Sketch mode | **Yes** — grid, DRO, snap chip, mode strip are instrument-grade (`05`, `08`, `44`) | — |
| Assembly | **Mostly** — solve-state + clash inspector (`43`) are ahead of the bar | pick-square blankets, flat framing |
| Drawings | **Yes (scoped)** — sheet, title block, hidden lines read real (`40`) | sparse sheet interactions (no zoom/pan evident) |
| Registers / sign-in | Sign-in distinctive (`01`); registers templated (`02`) | web-table look |

**States under stress:** deep 16-feature tree stays legible with honest
ERR→SKIP cascade (`23`); broken rebuild is exemplary — typed error, message,
rollback, last-good body preserved (`24`); clash stress with 14 interfering
pairs renders red tint + per-pair mm³ without layout strain (`43`). Busy
states exist in code (Solving…/Projecting…/aria-busy) — not visually
audited this pass.

**Consistency & tokens:** zero hex literals in `apps/web/src`; the viewport
imports `@loft/design/tokens` (one palette, two renderers holds); primitives
carry the surfaces. Signature element (brass scribe + engraved data panels)
is present on every workspace. Discipline: intact.

### The five changes that most move "reads as a Fusion/Plasticity competitor"

1. **Fix the command-band width tiers + overflow clamp** (P0) — tools must
   never vanish or scroll the app; add the e2e width guard.
2. **Selection that keeps the studio look and localizes to the feature** —
   kill the whole-body clay swap; brass edges + feature-face overlay.
3. **Live extrude ghost while editing** — the first surface where Loft
   *responds before commit*; template for fillet/datum/draft.
4. **Cursor-driven topology highlight** replacing candidate-square blankets
   (mate + measure), plus a visible body hover glow.
5. **A viewport right-click menu** (fit, snaps, sketch-on-face, measure,
   suppress) — the cheapest large step toward incumbent muscle memory.

Running checklist (this pass): `TopToolbar`/`ToolButton` width tiers 🔴 (P0)
· tooltip stacking 🔴 · `ModelMesh` selection/hover 🔴 · feature editors
(preview) 🔴 · context menus 🔴 · viewport atmosphere/grid/ViewCube ✅ ·
chrome honesty (part+assembly inspectors, view rail, units, export) ✅ ·
error/stress states (`23`/`24`/`43`) ✅ · sketch mode ✅ · drawings sheet ✅
· registers ✅ (de-templatized 2026-07-25 — one `DocumentRegister`, recency +
unstarted + units replace the duplicate date columns) · token discipline ✅.

**Process note (relaunch):** predecessor's evidence 01–40 reviewed and kept;
41–45 (dense assembly, clash stress, 1280 sketch/editor) regenerated this
session. Stack :8030–:8032 + Vite :5193 booted and torn down; other
auditors' stacks untouched.

## 2026-07-30 pass — verification of the 07-25 → 07-29 surfaces + a systemic token defect

**Trigger.** ~25 commits since the 2026-07-24 hard audit; four specific claims
to verify (registers `9203126`, tapped-hole authoring `a8cf9ec`, honest clash
schedule `9e7f369`, cut ghost `92c9d5b`), plus a free sweep with the two lenses
that have historically found the worst defects: *is this chrome element wired*
and *does the UI assert something the backend never said*.

**Method.** Isolated native stack (gateway :8040, documents :8041, geometry
:8042 from fresh SQLite; Vite :5194 — all torn down, shared :8000–:8002 left
alone). Real Chromium at 1280×800, 1366×768, 1440×900, 1600×1000, 1920×1080,
1024×768; `reducedMotion: reduce` pass; keyboard-only pass on the register;
CSSOM + `getBoundingClientRect` measurement rather than eyeballing; the app's
Tailwind build inspected directly (`pnpm exec tailwindcss -c tailwind.config.ts
-i src/index.css -o …`). Committed founder shots re-read for the four claims.
No app code touched. Probe specs were temporary and are deleted; every number
below is reproducible from the repro line on each finding.

### Executive verdict

**Three of the four claims hold; one is overstated. And underneath all of them
sits a defect nobody has flagged in three audits: the design system silently
voids ~118 of its own utility classes**, so several *deliberately designed*
elements — including the feature tree's rollback bar, the tapped hole's thread
callout rules, and the active-tool brass scribe that the token docs call "the
accent is a line, never a fill" — **do not render at all**, the primary
toolbar's tool buttons are 16 px tall instead of the intended 28, and the
measure HUD renders at the top of the frame instead of above the view rail.
This is the "fix the primitive" rule failing at the root of the primitive: it
is one line of `tokens.ts` plus a guard, and it is the highest-leverage change
available.

Otherwise the burn-down is real and holds up under measurement: the 07-24 P0
(band width tiers) is properly fixed — the band measures itself
(`data-band-tier`) and `scrollWidth == clientWidth` at 1280/1440/1600/1920 with
INSPECT visible at all four; tooltips now win the stacking contest (`z-band`);
right-click exists; feature-localized face selection landed; a mouse legend
chip closed the orbit/pan/zoom discoverability gap; `prefers-reduced-motion`
is clean (zero transitioning transform/opacity/geometry properties under
`reduce`); focus rings are 2 px solid on every register control and the tab
order is correct.

### P1 — breaks a shipped surface

- **P1 — DESIGN SYSTEM — the closed `spacing` scale silently deletes ~118
  utility classes, and five visible elements with them.**
  `packages/design/src/tailwind-preset.ts:60` sets `spacing: mapPx(spacing)`,
  *replacing* Tailwind's scale with the closed one at
  `packages/design/src/tokens.ts:537`, which has no `1.5`, no `2.5` and no
  `px` step. Tailwind emits **no rule at all** for a utility whose step is
  absent — no warning, no build error — and Preflight zeroes `button` padding,
  so the intent just evaporates. Verified against the built CSS: `.py-1\.5`,
  `.gap-1\.5`, `.px-1\.5`, `.h-px`, `.w-px`, `.inset-x-1\.5`, `.bottom-16`,
  `.max-h-64`, `.w-24/40/44/48/52`, `.min-w-20/24/28` are **absent**; only
  `py-0.5 / 1 / 2 / 3 / 6 / 10` exist. 118 usages across 40 files. Confirmed
  user-visible consequences, each measured in the browser:
  - **The feature tree's ROLLBACK BAR does not exist.**
    `FeatureTreePanel.tsx:181,187,192` draw it as `h-px grow bg-brass` +
    `h-px w-3 bg-brass`, and the *hover* drop hint as `h-px grow
    bg-transparent group-hover:bg-etch` — all three collapse to 0 px. The word
    "ROLLBACK" renders with no line, and the drop slots (`rollback-slot-N`,
    measured 294×8 px) have **no hover affordance whatsoever**. *Scenario:* a
    Fusion user looks for the rollback bar to step back through the tree,
    sees a stray label, and concludes history rollback isn't there. Visible in
    every committed part shot (e.g. `docs/screenshots/hole-tapped-tree-desktop.png`,
    tree row 03 area — bare "ROLLBACK", no rule).
  - **The tapped hole's thread callout has no leader tick and no note rule.**
    `HoleEditor.tsx:633` (`h-px w-3 bg-brass`) and `:642`
    (`h-px grow bg-brass/40`) measure **12×0** and **223×0**. The code calls
    this "the one loud line in a quiet card"; it renders as plain brass text.
    Evidence: `docs/screenshots/hole-tapped-laptop.png` — "M10x1.5" with
    nothing either side of it.
  - **The active-tool brass scribe never renders, on the toolbar or in any
    SegmentedControl.** `ToolButton.tsx:168` and `SegmentedControl.tsx:86` are
    both `absolute inset-x-1.5 bottom-0.5 h-px bg-brass` — measured **0×0**
    with `aria-pressed="true"`. Selection is carried by ink colour alone, i.e.
    the token system's stated signature ("the accent is a line, never a fill")
    is not on screen anywhere.
  - **Every tool button in the primary command band is a 32×16 px target.**
    `ToolButton.tsx:139` `py-1.5` → computed `padding: 0px 8px`, so the button
    is exactly its 16 px glyph. Identical at 1280/1440/1600/1920. The doc
    comment two lines up promises "a comfortable ≥32px square hit target".
    Same cause makes `SegmentedControl` segments 15 px tall
    (`SegmentedControl.tsx:67`) and the new viewport context menu's rows
    **222×17 px at 23 px pitch** (`ContextMenu.tsx:237`, `gap-2.5 py-1.5` both
    dead — which is also why the menu's glyph sits flush against its label;
    see the cramped menu in the 1440 repro).
  - **The measure HUD renders at the top of the viewport.**
    `MeasureReadout.tsx:105,125,174` position it `absolute bottom-16
    left-1/2`; `bottom-16` is dead → `bottom: auto` → static position.
    Measured at 1440×900: `top: 90, bottom: 144` in a 900 px window, i.e.
    pinned under the command band and **partially occluded by the band's own
    "Measure M" tooltip**, at the opposite end of the frame from the picks the
    user is making.
  - **`AddInstancePanel.tsx:61` `max-h-64 overflow-y-auto` never caps or
    scrolls** — the add-part list is unbounded, so an assembly library of 40
    parts grows the panel past the frame. That is a missing long-content state
    created by the same defect.
  **Fix (primitive, one commit):** add the half-steps the design language
  actually uses to `tokens.ts` `spacing` — `"1.5": 6, "2.5": 10, px: 1` — and
  convert the one-off large widths (`w-24/28/40/44/48/52`, `min-w-20/24/28`,
  `max-h-64`, `bottom-16`) to either named `layout` tokens or arbitrary values
  (`w-[11rem]`), since those are genuinely outside a closed scale.
  **Then make it impossible to regress:** a unit test in `packages/design`
  that greps `apps/web/src` + `packages/design/src` for spacing-family
  utilities and fails on any step not present in `theme.spacing`. The failure
  mode is *silent*, so a guard is the deliverable, not the scale edit.
  *Repro:* `pnpm exec tailwindcss -c apps/web/tailwind.config.ts -i
  apps/web/src/index.css -o /tmp/built.css && grep -c 'h-px' /tmp/built.css`
  → 0.

- **P1 — assembly viewport — an UNVERIFIED pair is painted as a measured
  clash, and told to screen readers as "interfering".** The panel and the tree
  are honest (`AssemblyClashPanel.tsx:119-141`, dashed rule + UNVERIFIED
  stamp + parenthesised bound), but `AssemblyPage.tsx:841` hands the scene
  `clashIds.flagged` — the *union* — while the tree gets `measured` +
  `unverifiedOnly` separately (`:850-851`). `AssemblyScene.tsx:184-195` then
  gives that instance `data-clashing="true"`, the flag-red balloon, and
  `aria-label="…, interfering"`, and `InstanceMesh.tsx:82-88` gives it the
  full `clashTint`. *Scenario:* the kernel says "I could not measure this
  pair"; the hero surface says, in the alarm colour, "these parts interfere",
  and a screen-reader user is told it flatly. This is the same class as the
  false `CLASH` badge a prior audit caught — two of three surfaces were
  repaired, the third was not. Evidence:
  `docs/screenshots/clash-unverified-after-1280.png` — instance 3 is
  UNVERIFIED in both panels and red in the viewport. **Fix:** plumb a third
  state through `AssemblyScene`/`InstanceMesh` (`unverifiedInstanceIds`, as
  the tree already receives): desaturated/gauge edge-light rather than the
  flag tint, `data-clash-state="unverified"`, and an accessible suffix that
  matches the panel's words (", overlap unverified"). One clash language,
  *three* surfaces — for real this time.

- **P1 — hole editor — the tapped + countersink + blind form runs off the
  bottom of the frame and takes the tap-drill override with it.** Feature
  editors are bare `absolute top-3 w-editor` cards
  (`HoleEditor.tsx:396-405`) with no `max-height` and no scroll, unlike
  `FloatingPanel.tsx:36-37,96` which already encodes the clamp
  (`max-h-[calc(100%-4.5rem)]` + `min-h-0 overflow-y-auto`). Measured, C'sink
  + Tapped + Blind depth:
  | viewport | card bottom | `document.scrollHeight` | consequence |
  | --- | --- | --- | --- |
  | 1280×800 | 858 | 858 (> 800) | Cancel/Create off-frame; **root becomes vertically scrollable** |
  | 1366×768 | 858 | 858 (> 768) | tap-drill chip (770–797) **and** footer (810–857) unreachable |
  C'sink + Tapped alone already reaches 801 at 1280×800. *Scenario:* on a
  1366×768 laptop a machinist authors an M10 countersunk blind tapped hole
  and cannot reach the derived tap-drill chip — the single control the
  "derived-but-overridable" design exists for — nor Create; the page scrolls
  the top bar away instead. (Enter and the band's OK cell still commit, which
  is why this is P1 and not P0.) **Fix (primitive):** route every feature
  editor through one `EditorCard` built on `FloatingPanel`'s clamp — capped
  height, scrolling body, action footer pinned — so no editor can ever grow
  past the frame as verbs keep landing. Add a Playwright guard asserting
  `document.scrollHeight == clientHeight` with the tallest editor open at
  1280×800 **and** 1366×768.

- **P1 — hole editor — the Tapped checkbox promises a drawing callout that
  does not exist anywhere.** `HoleEditor.tsx:616`: *"Drills the tap drill and
  carries the callout to drawings — no helix is modelled."* The
  `IsoMetricThread` field is read in exactly one place in the backend —
  `services/geometry/src/geometry/features/evaluate.py:1901`, to validate the
  bore — and `grep -n thread` across `services/documents/src/documents/drawings.py`
  and `services/geometry/src/geometry/drawings/compose.py` returns only the
  word "threading/threaded" in prose. No sheet annotation, no BOM column, no
  PDF/DXF note, no STEP attribute. *Scenario:* a user ticks Tapped
  specifically because the UI told them the callout reaches the drawing,
  exports the sheet to a shop, and the shop receives a plain Ø8.5 bore with
  no thread spec — the exact failure mode the byte-identical-mesh problem was
  supposed to be solved for. **Fix:** either (a) change the copy today to what
  is true ("carries the M-designation on the feature; the tree shows it — the
  drawing note is not implemented yet"), or (b) land the sheet note. (a) is a
  one-line honesty fix and should not wait for (b). File (b) as the BACKLOG
  item that closes the tapped-hole story.

### P2 — clearly behind the bar

- **P2 — register — the sheet number presents itself as a filing identity and
  is a row ordinal.** `DocumentRegister.tsx:208-210` documents `sheetNo` as
  *"Filing identity: '001'. Stable"* but computes `String(index+1)`
  (`:265`), and the create line's "next sheet number" is `documents.length+1`
  (`:197`). Measured: rows `001/002/003` for [Bracket plate, Motor mount…,
  Spindle housing]; delete Bracket plate → `001/002` now address Motor mount
  and Spindle housing. *Scenario:* a user notes "sheet 002" in a change note
  or a message, deletes an older part, and 002 silently means a different
  part. This is a readout claiming more than it knows — the same lens as the
  false clash badge, at lower stakes. **Fix:** cheapest honest version — make
  the column an ordinal and say so (`#` header, `sr-only` "Row", and drop
  "filing identity" from the doc comment); the durable version is a stored
  per-owner monotonic sequence on the document row, which is a documents-service
  change and worth filing separately if the founder wants real sheet numbers.
- **P2 — primitives — `PanelActionCell` is a `pointer-events-none` disabled
  trap, and so is `PickButton`.** `packages/design/src/primitives/Panel.tsx:101`
  sets `disabled:opacity-50 disabled:pointer-events-none` on the cell used
  for **every editor footer action and every export cell**, and it uses the
  native `disabled` attribute — so a gated Create/Save/Export can be neither
  hovered nor focused and has nowhere to hang a reason.
  `HoleEditor.tsx:159-179` `PickButton` does the same (`disabled={!hasFace}`
  on "Pick a point", `cursor-not-allowed`, no reason). `ToolButton` solved
  this correctly two audits ago (`aria-disabled` + `aria-describedby` caption,
  reachable by mouse *and* keyboard — verified live: `aria-label="Hole —
  create a body first"`). *Scenario:* Create is grey, the user cannot discover
  why by hover or by Tab. **Fix:** give `PanelActionCell` the `ToolButton`
  treatment — `aria-disabled`, inert on activation, a `disabledReason`
  rendered as a described-by caption — and add the same to `PickButton`
  (or better, promote `PickButton` into the design package, since three
  editors now hand-roll it).
- **P2 — assembly — the grounded instance's balloon number is replaced by its
  state, so the number the clash schedule and BOM cite cannot be found in the
  viewport.** `AssemblyScene.tsx:200` renders `instance.grounded ? "⏚" :
  instance.balloon`. In `clash-unverified-after-1280.png` the schedule reads
  "①1 ✕ ②2" and there is no "1" anywhere on the canvas. *Scenario:* a user
  reads a clash row, looks for part 1 to move it, and can't locate it.
  **Fix:** keep the number always; carry "grounded" as an adjacent anchor tick
  or a brass ring on the balloon. Identity is not a state slot.
- **P2 — assembly panels — `①`/`②` are decorative glyphs that look like the
  numbers next to them.** `AssemblyClashPanel.tsx:132` renders
  `①{a.balloon} ✕ ②{b.balloon}` and `AssemblyTreePanel.tsx:228` the same, so
  a clash between balloons 3 and 5 reads **"①3 ✕ ②5"** and a screen reader
  says "circled digit one three multiplication circled digit two five". *Fix:*
  drop the decorative glyphs (the balloon numbers already are the identity) or
  make them real circled balloons rendered as a shared `Balloon` primitive the
  viewport also uses; either way give the pair an `aria-label` such as
  "balloons 3 and 5".
- **P2 — pre-pick affordances are still DOM-square blankets** (07-24 P2, not
  fixed; evidence refreshed this pass at 1440: ~22 white squares and diamonds
  scattered over a six-face plate the moment Measure is armed, and 7 squares
  for a hole's face pick). Reads as debug markers; Fusion/Plasticity highlight
  the topology under the cursor. **Fix unchanged:** raycast hover highlight on
  real topology; keep the DOM nodes as invisible test hooks.
- **P2 — touch/tablet ergonomics are unmet product-wide.** Every interactive
  element measured in the chrome is 15–23 px tall: command-band tools 32×16,
  register `part-delete` 53×15 and `part-open` 84×18, `breadcrumb-register`
  39×15, `document-unit-select` 38×19, `feature-select-N` 232×20,
  `feature-suppress-N` 18×18, `rollback-slot-N` 294×8, `nav-cue-dismiss`
  60×19, assembly balloons 24×24. Most survive WCAG 2.2 SC 2.5.8 (AA) only
  via the **spacing exception**, which is nowhere written down as a design
  decision — and the new context menu (222×17 at 23 px pitch) fails it
  outright. The design mandate's own floor ("touch targets on tablet-class
  viewports") is currently not met on any surface. **Fix:** decide and
  document the target-size policy in `packages/design` (a `--target-min`
  vertical padding applied by the primitives, plus an explicit "spacing
  exception, ≥24 px pitch enforced" note), and make the context menu 24 px+
  per row. Fixing the P1 spacing defect above recovers a large part of this
  for free (tools 16→28, segments 15→27, menu rows 17→29).

### P3 — polish / taste

- **P3 — register, day one, says the same thing three times.** With a fresh
  drawer, LAST WORKED is "NOT STARTED" on every row and FILED is the same date
  on every row — structurally the *same* redundancy the rebuild was made to
  remove (two identical ISO dates), just with a nicer vocabulary. It resolves
  itself as soon as work happens, so it is taste, not a defect; but consider
  suppressing FILED while it is identical across the visible rows, or
  demoting "Not started" to a quiet gutter dot so the column is empty until
  it has something to say.
- **P3 — register row baselines don't agree.** UNITS and FILED sit ~3 px above
  the NAME/LAST WORKED baseline (`text-xs` data cells with `align-middle`
  against a `text-md` name); a precision index should have one baseline.
  Fix in `DocumentRegister.tsx:390-426` with a shared cell class rather than
  per-cell type sizes.
- **P3 — `documentActivity` "unknown" renders a bare "—" with no title**
  (`DocumentRegister.tsx:420`, `lib/activity.ts:39-40`). Rare (unparseable
  stamp) but it is an em-dash with no meaning attached — the same nit the
  07-24 pass filed against the empty SOLVE readout. Say "Unknown".
- **P3 — relative age never refreshes.** `documentActivity(..., Date.now())`
  is evaluated at render and the query is `staleTime: 30_000` with no
  interval, so a register left open reads "2 min ago" indefinitely. A 60 s
  tick (or `refetchInterval`) makes the column true.
- **P3 — the `№` gutter header is a glyph, not a name.**
  `DocumentRegister.tsx:248` — screen readers announce "numero sign". Use a
  visible `№` with `sr-only` "Sheet number" (or "Row", per the P2 above).
- **P3 — the tapped/counterbore badge asymmetry is defensible but
  under-serves the tree.** The stated rule ("badge only what the viewport
  cannot show") is principled and I would not call it inconsistent. It does,
  however, optimize for the wrong reader: the tree is scanned precisely when
  the viewport is showing something else — another orientation, a section, a
  different zoom — or when the recess is on a hidden face. In a 20-feature
  tree with six holes, "which one is the counterbored one" costs six clicks.
  A callout-shaped badge is the consistent generalization of what already
  shipped: `hole · M10x1.5`, `hole · ⌴Ø14`, `hole · ⌵90°`. Cost is ~10 lines
  in the same formatter that produces the thread badge, no new data. Worth
  doing; not urgent.
- **P3 — the register has no search/filter/sort.** Fine at 3 rows; at 100
  parts (no server limit — `fetchParts` returns the whole list) the create
  line is a full scroll below the fold and there is no way to find a part by
  name. Not a defect today; file it before the first user with a real drawer.

### Verdicts on the four claims

1. **Registers "read as a precision index" — HOLDS**, at 1440 and at
   1280×800 (measured: fits, no root scroll, height 667/800). The gutter +
   scribe + ruled remainder genuinely kill the centered-card-in-a-void read,
   and the information change is the right one: LAST WORKED and UNITS are real
   per-document facts where CREATED/UPDATED were one fact printed twice. Two
   caveats above (sheet-number honesty P2, day-one redundancy P3) and one
   ergonomic miss (DELETE is a 53×15 px target). **On the deliberately-omitted
   columns:** agreed on "has a body" and "has drawings" — a modeler does not
   scan for those. **"Is broken" is the one I would add**, because the most
   expensive surprise a returning engineer gets is opening a part whose
   rebuild fails, and the register is where they choose. It need *not* cost an
   evaluate-per-row: the honest cheap version is a persisted
   `last_eval_status` + `last_eval_at` on the document row, written by the
   gateway whenever an evaluate returns, surfaced as an exception flag in the
   same column that already carries "Not started" (and stale-marked if
   `updated_at > last_eval_at`). That is a documents-service migration plus
   one gateway write — real work, but bounded, and it makes the register the
   first surface that tells the truth about the drawer's health.
2. **Tapped-hole authoring — the model HOLDS, the execution has two
   failures.** Orthogonal toggle rather than a fourth Type segment is right
   and matches the wire; the derived-but-overridable tap-drill chip with brass
   "you're on the standard" state is exactly right; the `hole · M10x1.5` tree
   badge is right and reads well. But: the drawings promise in the checkbox
   description is **false** (P1), the callout's leader tick and note rule —
   its whole visual identity — **do not render** (P1 spacing defect), and at
   1366×768 the tap-drill chip is **off-screen** (P1). "Still legible at
   1280×800 now that it grew a row": yes for Simple+Tapped (584 px tall,
   fits); no for C'sink+Tapped (801) or C'sink+Tapped+Blind (858).
3. **Interference UNVERIFIED reads as indeterminate — HOLDS in the schedule,
   FAILS in the viewport.** In the panel the work is done by the UNVERIFIED
   stamp, the parenthesised figure and the "at most" caption, and the
   plain-language footnote — that trio reads as "not established", not as an
   error and not as a warning, and the split eyebrow (`Interference · 1 · 1
   unverified`) is genuinely honest. The dashed 2 px etch left rule
   contributes almost nothing at that scale (it reads as *absent* rather than
   as *phantom*); if you want the stroke to carry weight, make it a wider
   dashed rule or a hatched gutter. And the third surface — the hero one —
   still says CLASH in red (P1).
4. **Cut ghost "reads as a subtraction" — OVERSTATED.** What is true and
   verified: the warm brass metal is gone, and the e2e pixel assertion for
   that is honest and worth keeping. What is not true: the ghost's
   **silhouette is identical to the ADD ghost's** — the same full cylinder,
   same outline, same footprint standing above the plate's top face
   (`extrude-cut-ghost-before-desktop.png` vs `-after-desktop.png` differ
   essentially in hue) — so the *shape* still says "a boss" and only the
   colour temperature says "a cut". Cold grey translucency over bright
   machined aluminium reads as smoked glass, not as a void; `BackSide` removes
   the near walls, which takes away the solid read without adding a cavity
   read. Neither benchmark previews a cut this way: Fusion/Plasticity show the
   **resulting body** with the material already gone. **Fix, in order of
   cost:** (a) cheapest real improvement — render the tool volume's
   silhouette as a dashed hidden-line outline plus a dark inner shadow at its
   footprint *on the body's face*, so the read is "a hole is coming here";
   (b) correct — preview the boolean result (the geometry service already
   evaluates; a debounced preview mesh is the same seam the extrude ghost
   already owns) or stencil/clip the body with the tool volume client-side.
   Until then, the honest claim is "a cut no longer previews as added metal",
   not "a cut reads as a subtraction".

### Running component checklist (this pass)

`packages/design` spacing scale + utility guard 🔴 **(P1, new — root cause of
five visible defects)** · `PanelActionCell`/`PickButton` disabled reasons 🔴 ·
feature-editor height clamp 🔴 · `AssemblyScene`/`InstanceMesh` unverified
state 🔴 · Tapped-hole drawings copy 🔴 · `DocumentRegister` sheet-number
honesty 🔴 · pre-pick topology highlight 🔴 (07-24 P2, still open) · touch
target policy 🔴 · `TopToolbar`/`ToolButton` width tiers ✅ (07-24 P0 fixed —
measured no root scroll and INSPECT visible at 1280/1440/1600/1920) · tooltip
stacking ✅ (`z-band`) · viewport context menu ✅ (exists; row density is the
P2) · feature-localized face selection ✅ · orbit/pan/zoom legend ✅ ·
`prefers-reduced-motion` ✅ (measured clean under `reduce`) · visible focus +
register tab order ✅ · WCAG-AA contrast ✅ (gauge 7.2:1 / mist 13.2:1 /
flag 6.5:1 on anvil; no new hex outside `packages/design`) · zero hex literals
in `apps/web/src` ✅ · registers (identity + information) ✅ · clash schedule
+ tree badges ✅ · viewport atmosphere/grid/ViewCube ✅.

### The five changes that most move the bar now

1. **Fix `spacing` + add the silent-utility guard** (P1). One scale edit plus
   one test recovers the rollback bar, the thread callout, the active scribe,
   28 px tool buttons, the measure HUD's position, and a bounded add-part
   list. Nothing else on this list is close to that ratio.
2. **Make the viewport tell the truth about UNVERIFIED** (P1) — the third
   surface of a three-surface language.
3. **One clamped `EditorCard`** (P1) so no feature editor can outgrow the
   frame as verbs keep landing, and its footer is always reachable.
4. **Fix the Tapped copy today; file the drawing note** (P1) — never let the
   UI promise an output the pipeline doesn't produce.
5. **Preview the cut as removed material** (claim 4) — the extrude ghost was
   the first place Loft responds before commit; making it *correct* is what
   turns it from a colour change into the Fusion/Plasticity read.

**Process note.** Two of the five biggest findings this pass were invisible to
every previous audit because they were *measurements*, not looks: a 0×0
element and a 16 px button both photograph as "dense and quiet". This
checklist now carries a standing item: **at every full audit, measure — assert
`getBoundingClientRect` on the elements the design docs call signatures, and
diff the built CSS against the utilities the source asks for.** A design system
that fails silently needs a gate, not an eye.

## 2026-07-30 — FLOW AUDIT (founder-directed: "keep auditing as I did")

Founder's own pass on 07-30 landed four hits by walking screens and asking what
a real user hits (timeline placement, component enablement/opacity, "placement
face looks like a text box", units/mass in settings). Those are filed as
UI-W1…W5 + #57/#58 with the design record in
`docs/design/ui-wave-tool-grade.md`. This pass continues in the same method —
**walk the flow, ask what the user actually experiences** — rather than
inspecting components in isolation. Read-only on app code.

The recurring defect class this codebase produces is now well established, at
four instances: **a surface asserting something it does not know.** The false
CLASH badge, the Tapped checkbox's drawing-note promise, MASS PROPERTIES with
no mass, and F2 below. Audit for it directly.

### F1 (P1, data loss + an inverted label) — Exit discards a sketch; the caption says Esc does

`SketchStrip.tsx:978-991`. The Exit button renders
`caption={bound ? "Esc closes" : "Esc discards"}` with
`aria-label="Exit sketch (discards unsaved entities)"`, and calls
`onClick={exit}` → `useSketchStore.exit` = `set({ ...INITIAL })`
(`sketch/store.ts:856`) — every unsaved entity gone, one click, **no
confirmation**, and no undo path because the sketch was never persisted so the
history stack has nothing to restore.

The label is **exactly inverted**. `Esc` at rest does NOT discard: the sketch
cascade (`PartPage.tsx:967-991`) resolves `escapeAction(...)` → `"exit"` only
when no editor, no pending placement, `tool === "select"` and no selection
(`sketch/tools.ts:376-387`), and that branch calls **`finishSketch()`** — the
same callback wired to `onSave` at `PartPage.tsx:3553`. So Esc **saves**.

Both directions harm:

- A user who wants to throw the sketch away presses Esc, believing the caption,
  and instead **persists a sketch they meant to discard**.
- A user who wants to keep the work avoids Esc for the same reason, clicks the
  button labelled Exit, and **loses everything without being asked**.

Fix: make the caption describe the key's real behaviour ("Esc saves"), and put
a confirm in front of a discard that destroys unpersisted entities — one that
states the count ("Discard 14 entities?"). This is the only finding in this
pass that destroys user work.

### F2 (P1, overstated surface — instance #4) — "Up to date" is derived from fetch state, not staleness

`InspectorPanel.tsx:140`:
`{error ? "Error" : isFetching ? "Meshing…" : "Up to date"}`.

"Up to date" therefore means *"no request is in flight and the last one did not
error"* — it does **not** mean the body on screen reflects the current feature
tree. Any path that mutates the tree without the mesh query being in flight
shows a stale body under a label claiming it is current. In a CAD tool, "the
geometry you are looking at is current" is precisely the claim a user must be
able to trust before exporting or dimensioning.

The honest source **already exists and already shipped**: `c98c454` added
`derive_part_eval_state` (`py_kit/schemas/parts.py`) — a 4-state fold
(`never | ok | failed | stale`) whose staleness is derived from the monotonic
`tree_version`, not from timestamps or fetch state — and it is already consumed
by the register. The part inspector ignores it. Cheap fix, high trust value.

### F3 (P2) — Deleting a feature others consume fires with no warning

`PartPage.tsx:2647`, `deleteFeatureAction`: no confirmation and no dependency
check. Delete `Sketch1` while `Extrude1` consumes it and the delete simply
succeeds; the user discovers the consequence when the extrude turns red on the
next evaluate. Undo exists, so this is recoverable rather than destructive —
which is why it is P2 and not P1 — but "let them find out" is not how a tool
of this class behaves. Fusion names the dependents before proceeding. We
already have the dependency information: the guard added for undo-vs-drawings
(P2 #16) established that we can reason about what a change breaks.

### F4 (P2) — Keyboard-first, with nowhere to learn the keyboard

The app deliberately trains shortcuts in button captions — `Esc`, `Enter`, `G`
for snap, `M` for measure, the constraint letters, the undo/redo chords in
`lib/undoRedoShortcut.ts` — and the design docs call it keyboard-first. There
is **no shortcut reference anywhere**: no `?` overlay, no help panel, no
cheatsheet. Every binding is discoverable only by hovering the one control that
happens to mention it, and the sketch letter vocabulary (where selection
presence decides whether a letter draws or constrains — `PartPage.tsx:958-960`)
is not written down in the product at all.

A `?` overlay listing the active surface's bindings is a small, self-contained
addition, and it is the cheapest single thing that makes the app feel
professional to a new user rather than opaque.

### Confirmed healthy (checked, not assumed)

Not everything probed was broken; recording the passes so later passes don't
re-litigate them.

- **Feature rename works** — inline in the tree, Enter commits, Escape
  abandons (`FeatureTreePanel.tsx:68-73`).
- **Drawing-from-part is contextual** — `PartPage.tsx:1846` calls
  `createDrawing`, so the flow does not force a trip to the Drawings register.
- **Part/drawing delete does confirm** — `DocumentRegister.tsx:354-420`, and
  the confirm takes the row over rather than firing a modal.
- **First-run guidance exists** — `NavCue` with a "Got it" dismiss, plus an
  empty-scene call to action (`PartPage.tsx:3282`).
- **Grid snap defaults ON** (`sketch/store.ts:282`, `snapEnabled: true`),
  which is the correct polarity and consistent with the UI-W5 decision that
  entity snapping should also default on with a modifier to suppress.
- **Stale-version conflicts are handled** — `deleteFeatureAction` retries once
  on `StaleTreeVersionError` with a re-fetched `tree_version`.

### Method note for the next pass

The two most valuable findings here (F1, F2) came from **following a control to
what it actually calls** rather than reading its label — F1 is a caption that
contradicts its own key binding, F2 is a status string computed from the wrong
variable. Neither is visible in a screenshot, and neither would fail a test
that asserts the label renders. The standing measurement item from the 07-30
pass gets a sibling: **for every status/affordance string, trace the value it is
derived from and confirm the string is entitled to make that claim.**

### F1 FIXED · F2 CORRECTED AND RE-SCOPED (same-day follow-up)

**F1 shipped.** `Esc` moved to the SAVE button, where the binding actually goes
(`escapeAction → "exit" → finishSketch`, the `onSave` handler). Exit now states
what it would destroy (`discards 4`) and asks first when — and only when —
discarding would lose unpersisted entities; a bound sketch's edits are already
saved, so it still exits in one click. The prompt is DERIVED
(`confirmingDiscard && !bound && entityCount > 0`) so saving or deleting the last
entity behind an armed confirm retracts it, instead of leaving a warning about
work that no longer exists.

Gated by 9 component tests, **mutation-verified**: reverting the guard to the old
`onClick={exit}` fails 5 of them, including "does not discard on the first click".

**F2 was mis-filed — correcting it rather than leaving it to mislead.** The
quoted line (`InspectorPanel.tsx:140`) is real, but `InspectorPanel` is used only
by `ModelerPage`, the box-primitive demo route. **The part workspace uses
`BodyInspector`**, fed a typed 4-state `BodyStatus` from `PartPage.tsx:3264`.

The SUBSTANCE survives the correction — that status is still computed from
request state, not from staleness:

```
regenFailed ? "error"
  : regenerating || (meshGlbId !== null && !bodyPresent && body.isFetching) ? "regenerating"
  : evaluation.isFetching ? "evaluating"
  : "up-to-date"
```

But the SEVERITY does not, so P1 was wrong. Every in-app mutation path calls
`refreshTreeAndBody()`, so the window where "Up to date" is shown over a stale
body is a transient race between mutation and refetch, not a persistent false
claim. The real exposure is a change this session did not make — a concurrent
edit arriving over the gateway's WS fan-out — where nothing invalidates and the
label would keep asserting currency indefinitely.

Re-scoped to **P2, and it is a contract change, not a frontend patch.** The
honest fix compares the `tree_version` the displayed body was BUILT from against
the part's current `tree_version` — the same monotonic discriminator
`derive_part_eval_state` already uses server-side. The evaluation/tessellation
response does not currently carry that provenance, so this needs a schema field,
`just gen`, and then the readout; guessing at a frontend-only fix would produce a
second status that also does not know what it claims. Filed with that shape
rather than half-done.

**Method note.** F2 is a reminder for this checklist: `grep` finding a string
does not establish that the string is on the screen the user is describing. Two
inspectors exist, one is a demo route, and the panel in the founder's screenshot
was the other one. Confirm the render path — which route mounts the component —
before assigning a severity to what it says.

### 2026-07-30 — RULING: selection colour differs between the tree and the timeline (UI-W1 handback)

The timeline agent flagged a deliberate divergence for a ruling rather than
picking silently, which is the right instinct — recording the decision so it
does not get re-litigated or quietly "fixed" by a later pass.

**The situation.** A selected feature-tree row takes a brass left-rule. A
selected timeline chip does NOT: it takes the strip's brightest border
(`border-mist`) plus a lifted `bg-hairline` seat. Two adjacent surfaces, two
selection languages, same underlying selection.

**Ruling: keep the divergence.** The design mandate says spend boldness in one
place, and the operative scope of "one place" is the SURFACE, not the app. Inside
the strip, brass belongs to the travel stop, because the stop is the only thing
whose *position carries meaning* — that is the whole metaphor. A brass chip
beside a brass stop would put the accent on two different kinds of thing at once
and the stop would stop reading as the position indicator. The tree has no travel
stop, so brass is unclaimed there and selection can have it.

Stated as a rule for future surfaces: **brass marks the single position/attention
indicator a surface owns; where a surface has one, selection must find another
cue.** That is a per-surface budget, not a global palette mapping.

**Why the inconsistency is tolerable in practice, and this is load-bearing to
the ruling rather than a consolation:** the two selections are SIMULTANEOUS.
Clicking a chip selects the feature, so the tree row lights at the same moment.
The user sees both cues co-occur on their first click, which teaches the mapping
instead of leaving them to infer it. If a future change ever lets the two
selections diverge in time — one lit without the other — this ruling should be
revisited, because the teaching mechanism would be gone.

**Not ruled on, deliberately left to frontend-qa:** whether `border-mist` is
sufficiently distinguishable from the unselected chip border at 1280 for a
low-vision user. That is a contrast measurement, not a design principle, and it
should be measured rather than argued — the standing lesson from the 07-30 pass
where a 0×0 element and a 16 px button both photographed as "dense and quiet".

### Also recorded from UI-W1, so the reasoning is not lost in an agent report

- The plan's stated 44 px strip height was WRONG and was overridden: its own
  wireframe stacked eyebrow + chip + ordinal + name, which cannot fit 44 px
  alongside the 32 px touch floor `tokens.ts` had just committed to. 48 px, with
  single-row chips. A plan that contradicts a policy the same repo just adopted
  loses to the policy.
- The travel stop's focus ring is `mist`, not the house brass: a brass ring
  around a brass blade is not a visible focus indicator (WCAG 2.4.7). Worth
  generalising — an accent-coloured focus ring is invisible on an
  accent-coloured control, so focus indication must contrast with the CONTROL,
  not merely exist in the palette.
- No `⇥` glyph on TO TIP (tofu risk in Fragment Mono); the label plus an
  `INCLUDE ALL` caption carry it. Consistent with preferring ASCII outside
  markdown.
- `p1-rollback-bar-*.png` (4 files) were DELETED rather than refreshed, because
  they documented an element that no longer exists. A screenshot of a deleted
  control is worse than no screenshot: it reads as current.

## 2026-07-30 — MEASUREMENT PASS: the timeline strip (UI-W1, `1a27804`) + the part workspace's status honesty (`b4e075f`)

Independent QA on the two surfaces shipped in the last few hours, by an eye that
did not build either. **Method: measurement, not photography.** Every number
below comes from a real browser driving committed HEAD — `getBoundingClientRect`
and `getComputedStyle` in-page, plus pixel sampling of actual screenshots for
the colour claims. The standing lesson (a 0x0 signature element and a 16 px
button both photograph as "dense and quiet") is why: three of the seven findings
here are invisible in a screenshot and two of them contradict a comment in the
source that asserts the opposite.

**Rig.** Native container-free stack on isolated ports (geometry :8042,
documents :8041, gateway :8040, Vite :5183 — the shared :5173/:8000-:8002 were
left untouched for the concurrent screenshot agent), fresh SQLite, Playwright
Chromium at 1366x768 and 1280x800, `deviceScaleFactor: 1`. Parts seeded through
the real gateway: a sound 3-feature part, the broken r50-fillet part
`body-status.spec.ts` uses, and 9/14-feature builds. All processes started for
this pass were killed at the end. **Measured vs inferred is labelled on every
claim.** No PNGs are committed with this pass (the brief scoped writes to this
file); the harness was temporary and removed — everything reproduces from the
numbers stated.

### The deferred question, answered: `border-mist` on `bg-hairline` clears, by 3.1x

The 07-30 ruling deliberately left "is a selected chip distinguishable ENOUGH
from an unselected one at 1280 for a low-vision user" to measurement. Measured,
at both widths, pixel-sampled from the rendered strip (no opacity, filter or
blend anywhere in the chain — the sampled pixels equal the token values byte for
byte, so the tokens ARE the render):

| pair | measured | floor |
| --- | --- | --- |
| selected border `mist` vs unselected border `hairline` | **9.38:1** | 3:1 (SC 1.4.11, state info) |
| selected border `mist` vs the strip ground `anvil` | 13.21:1 | 3:1 |
| selected border `mist` vs its own `hairline` seat | 9.38:1 | 3:1 |

Identical at 1280x800 and 1366x768 (chip geometry is width-invariant: 32.00 px
tall, border 1 px, same tokens). **Verdict: the divergence from the tree's brass
is safe and the ruling stands.** A 9.38:1 step between states is 3.1x the
non-text floor and larger than most products' selected-state deltas; nothing
about it needs to change, and it does not need to take brass.

Two caveats that the same measurement produced, and they are findings in their
own right (P2-A and P2-B below): the reason the delta is so large is that the
**unselected** chip has effectively no edge at all, and the "lifted seat" that
was supposed to be the redundant half of the selected cue lifts by 1.41:1.

### P1 — part workspace / EXPORT strip — the gated export is under the fold at 1366x768 again, and the partial-body notice is 100% invisible

MEASURED, at 1366x768, on the floating Inspector panel's scroll box
(`FloatingPanel` body, `max-h-cube-card` = `calc(100% - 152px)`):

| state | export strip rect | scroll box bottom | visible | hidden content |
| --- | --- | --- | --- | --- |
| feature error (`Fillet1 failed`) | y 536.5 -> 601.5 (65 px) | 580 | 43.5 of 65 px | 23 px |
| travel stop (`partial`) | y 560.5 -> 659 (98.5 px) | 580 | **19.5 of 98.5 px** | **80 px** |
| same, at 1280x800 | y 536.5 -> 601.5 | 602.5 | all | 0 px |

In the travel-stop case the notice — *"1 feature excluded by the travel stop.
The file will be the rolled-back body, and its name will say partial."* — sits
at y 609 -> 659, i.e. **entirely below the fold**, and the STEP/STL cells are cut
at their first 19 px. That sentence is the whole point of `exportGate`'s
"allowed, but the artifact is a prefix" branch: it is the only place the product
warns that the file you are about to download is not the part. It is currently
unreachable without discovering an unhinted scroll.

Why it regressed, COMPUTED from the measured tokens (labelled as computed): the
panel box is `main.height - 152`. Docking a 48 px strip shrank `main` from 668 to
620 at this height, so the box went 516 -> 468 px while the failed-state content
is 491 px. **It fit with 25 px of headroom before UI-W1 and is clipped by 23 px
after.** The `1280x800` row proves it is a height regression, not a width one.

The `partBuild.ts` docstring anticipated exactly this failure ("a panel that
spends four lines on a paragraph pushes the EXPORT strip below the fold at
1366x768, and the gated export is the most important thing on this panel") and
spent the one-line register form to avoid it. The measurement says the saving
was not enough, because the 48 px the strip took was not subtracted from the
panel clearance in the same change.

System-level fix (either, not both): (a) subtract `layout.timelineHeight` from
`hudLaneBottom` / `referenceCubeBand` — both were sized when `main` reached the
window bottom and the reference cube now sits 48 px higher too; or, better,
(b) **pin the title block's STATUS + EXPORT footer outside the panel's scroll
box**. A title block's footer is the one row that must never be the thing that
scrolls away, and pinning it makes the fold immune to the next 48 px anything.

### P2-A — timeline strip — the chip's resting border is 1.54:1, so "solid vs dashed" carries no information

MEASURED (computed styles, confirmed by pixel sampling at x=216, y=24 of the
rendered strip: border `rgb(44,55,71)`, seat `rgb(15,20,26)`, ground
`rgb(22,29,39)`):

| pair | measured | floor |
| --- | --- | --- |
| unselected chip border `hairline` vs its `carbide` seat | **1.54:1** | 3:1 |
| unselected chip border `hairline` vs the `anvil` ground | **1.41:1** | 3:1 |
| the way line's dash, `etch` vs `anvil` | 3.06:1 | 3:1 — passes |
| the dim cue, `mist` name vs `gauge` name | 1.84:1 | — |

The source comment says: *"chips past the stop take a dashed outline AND dim, so
the cue is redundant and never load-bearing alone."* Measured, that is **false**.
The dashed outline is drawn in `hairline` at 1.54:1 against the chip it outlines
— below the 3:1 floor this repo applies to itself (`etch`'s own docstring:
*"Interactive control borders (3.06:1 on anvil — WCAG 1.4.11)"*). So the dash is
not a second cue; the **dim is load-bearing alone**, and it is a 1.84:1
luminance step on an 11 px name.

The same 48 px strip gets it right on the rail and wrong on the chip: the way
line's dashes are `etch` and read cleanly; the chips' are `hairline` and do not.
Answering the founder's question directly — **the dashed-past-the-stop encoding
does NOT read on the chips without a legend at either width**; what actually
reads is the way line's dash plus the dim, and only the way line's dash is above
the contrast floor.

Fix at the token, not the instance: give the chip's resting/rolled-back border
`etch` instead of `hairline`. That buys the chip a boundary that says "control"
(3.35:1 on its seat) and a dash that is actually visible, and it costs the
selection delta nothing that matters — `mist` vs `etch` is still **4.31:1**,
well above the 3:1 state floor, with the seat and the dim on top. `etch` is
already the hover value, so hover would need one step of separation (either
`mist`-at-rest-on-hover, or a seat change on hover).

### P2-B — timeline strip — the selected chip's "lifted seat" lifts by 1.41:1

MEASURED: `bg-hairline` on `bg-anvil` = **1.41:1**; the same seat against an
unselected chip's `carbide` = 1.54:1. The selection story is documented as
"brightest EDGE plus a lifted seat"; the seat half contributes essentially
nothing perceptually. Not a WCAG failure (the edge carries it at 9.38:1), but
the redundancy claimed in the design record does not exist, and this is the
second finding in this pass where a comment asserts a redundancy the pixels do
not have. Fix: the palette has no surface token brighter than `hairline`, so the
system-level answer is a new raised-surface token (a `bezel` step around
`#39465A`, ~1.9:1 on anvil) used by every "seated/selected row" in the product,
rather than a one-off in the strip.

### P2-C — `BandActionCell` (design primitive) — the gated cell's REASON measures 2.13:1 at 9 px

The primitive gates with `aria-disabled` rather than the native attribute
**specifically so the reason can be read** — its own docstring says so, and the
07-30 pass filed the same defect against `PanelActionCell`. MEASURED on the
rendered pixels of TO TIP in its gated state (brightest pixel of each text run
against the anvil ground; the whole button carries `opacity-40`):

| run | size | measured contrast |
| --- | --- | --- |
| label "To tip" (`mist` @ 0.4) | 10 px | 3.05:1 (analytic blend 3.24:1) |
| caption "Already at the tip" (`gauge` @ 0.4) | **9 px** | **2.13:1** (analytic 2.25:1) |

So the explanation is reachable by mouse and keyboard (verified: `aria-disabled`,
NOT native `disabled`, focusable, and it swallows activation) and cannot be
read. Disabled text is technically exempt from SC 1.4.3 — but a reason nobody
can read defeats the entire purpose of choosing `aria-disabled`, which is the
standard this component set out for itself.

Also: `text-[9px]` is the **only arbitrary font size in `packages/design`
primitives or `apps/web/src`** (grepped) and sits below the committed scale floor
(`fontSize["2xs"] = 10`). Fix in the primitive, which fixes CreateStrip's OK/
Cancel in the same stroke: drop `opacity-40` for an explicit disabled-foreground
token that holds >= 4.5:1 on `anvil`, and put the caption on the scale at 10 px.

### P2-D — timeline strip — during a rollback write, three affordances go inert and none of them says why

MEASURED with the rollback response held for 2.5 s (route delay), reading
computed styles mid-flight:

- the **stop**: `aria-disabled="true"` (good, not native) but `opacity: 1`,
  `cursor: ew-resize`, and it still brightens to `brass-hover` under the pointer
  — it looks and feels draggable for the whole write and is inert;
- the **slots**: native `disabled` = `true`, no `title`, no reason — they leave
  the tab order entirely, which is the exact pattern the 07-30 pass removed from
  `PanelActionCell` ("unreachable while the cell was natively disabled");
- **TO TIP**: gated, caption still reads "Include all" — the caption is the place
  the reason lives, and during a write it states the wrong one.

Good half, measured: `data-busy` / `aria-busy` are set on the section, and the
head cell shows the optimistic pending position ("01/03") the instant you drag,
so the strip does communicate *that* something is happening. Fix: a held visual
on the stop (cursor + a dimmed blade), `aria-disabled` in place of native on the
slots, and a busy caption ("Working…") on TO TIP.

### P3 — timeline strip — the travel stop's focus ring renders as two loose bars, not a ring

MEASURED by pixel-diffing the same 44x53 crop focused vs unfocused: exactly four
pixel columns change (x=427-428 and x=453-454, `rgb(221,228,235)` = `mist`, 47 px
tall). **No top or bottom segment exists.** Cause: `outline-offset-0` on a
full-height element inside the way, whose `overflow-x-auto` computes `overflow-y`
to `auto` and therefore clips at the padding box; and the strip's bottom edge IS
the window's bottom edge, so the lower segment has nowhere to draw.

Not a 2.4.7 failure — two full-height mist bars at 13.21:1 against the ground are
a visible indicator — but it is not the ring that was designed. Fix: inset it
(`-outline-offset-2`), which the slot and TO TIP cells already do, so all four
sides land inside the clip.

**The mist-over-brass decision is vindicated by measurement, and worth keeping in
the record:** `mist` on `brass` is **1.67:1** — a brass ring on the brass blade
would have been invisible exactly as claimed. Against the surface the ring
actually sits on (`anvil`) it is 13.21:1. The generalised rule from the 07-30
notes ("focus must contrast with the CONTROL, not merely exist in the palette")
holds here, and every other new control's brass ring clears too: 8.65:1 on the
chip seat, 7.93:1 on the ground, and the chip's ring is pixel-verified as a
complete four-sided rounded rect.

### P3 — timeline strip — a scrolled way gives no sign there is more of the build

MEASURED at 1366x768 with 14 features: `scrollWidth` 1727 vs `clientWidth` 1138;
on mount the way scrolls the stop into view (`scrollLeft` 589), so chips 01-05
are off-screen to the left (chip 0 at x = -492) with no fade, arrow, or count
saying so. The head cell reads "14/14", which describes the stop, not the
scroll. Fix: a token-coloured edge mask on both ends of the way when
`scrollLeft`/right allows, plus `scrollbar-width: none`.

INFERRED (could not be measured here): headless Chromium reserved 0 px for the
horizontal scrollbar (`offsetHeight - clientHeight = 0`). A desktop Chrome with
classic scrollbars would take ~15 px out of a 48 px strip and collide with the
32 px chips. The mask fix above closes this too; worth verifying on a real
desktop browser before assuming it is fine.

### P3 — timeline strip / feature tree — a truncated feature name has no reveal

MEASURED: chip name clamps at `max-w-[7.5rem]` (120 px); a 37-character name
measures `scrollWidth` 189 and truncates. The full name IS in the accessible
name (`"A very long feature name for wrapping — fillet, step 3 of 3"` — good),
but there is no `title`, so a sighted mouse user cannot recover it. The tree row
has the same shape (`truncate`, no `title`). Fix once, in the shared row/chip
label, not twice.

### P3 — timeline strip — Escape does not cancel a stop drag, and the slider ignores half its keys

MEASURED: pointer-down on the stop, drag to slot 0, press `Escape` ->
`data-dragging` stays `"true"` and the pending position stays "01/03"; pointer-up
commits the rollback. Rolling back is reversible and fully visible, so this is
not the "Escape destroys work" class — but every other gesture in this product
answers Escape, and a drag with no abort is a small trust cost on a control whose
whole job is "how far does the build run". Also `role="slider"` implements
Left/Right/Home/End only; APG expects Up/Down and PageUp/PageDown as well.

### P3 — part workspace — rolling back below the first solid says "No body" instead of naming the stop

MEASURED: setting the travel stop to a sketch-only prefix drops `hasBody`, the
Inspector is replaced by the export-only panel, and `exportGate` reaches its
`!hasBody` branch **before** the `rolledBack` branch — so EXPORT reads "No body".
True, but it attributes the absence to nothing, when the user's own travel stop
caused it and the control holding it is 40 px below on screen. By `b4e075f`'s own
standard (name the cause, never let a surface assert less than it knows), the
honest reason is "No body at the travel stop". One branch reorder.

### Verified good — measured, no action

- **Nothing in the strip is decorative** (mandate 3c). Head cell position tracks
  the stop live including the optimistic value during a write; chips select and
  open the tree's row menu; slots travel; the stop drags and takes keys; TO TIP
  travels and states its own gate. Every element is wired.
- **Target sizes all clear the committed floor**: chips 32.00 px (comfortable),
  slots 24.00 x 47.00, stop 24.00 x 47.00, TO TIP 138.59 x 47.00. The tokens'
  claim that "nothing in the product now claims the essential exception" holds —
  the retired 8 px drop slots are genuinely gone, and nothing took their place.
- **Tab order and focus**: chip0 -> slot0 -> chip1 -> slot1 -> chip2 -> stop ->
  TO TIP, DOM order, every stop `:focus-visible` with a 2 px ring. (Note for a
  future pass, not filed as a defect: this is 2N+1 tab stops, so a 20-feature
  build costs 41 presses to cross — a roving-tabindex composite would be the
  standard answer if a keyboard user ever complains.)
- **Keyboard context-menu parity**: Shift+F10 on a focused chip opens the same
  row menu at the chip (x=144 for a chip centred at 144; flipped up to y=619 to
  fit) — not at 0,0, which is the usual failure of this pattern.
- **`prefers-reduced-motion`**: chip, slot and stop all report
  `transition-duration: 0s` under `reducedMotion: "reduce"`, and the way's
  `scrollIntoView` drops to `behavior: "auto"`.
- **Empty and loading states exist and are honest**: "No features yet — start
  with a sketch." (`gauge` on `anvil` = 7.18:1), position "—", TO TIP caption
  "Nothing built yet".
- **The viewport is still the hero at the tightest width.** Canvas 1366x620 =
  **80.7%** of the frame at 1366x768 (1280x652 = 81.5% at 1280x800); panels
  float over it; `documentElement.scrollWidth == clientWidth` at both widths, so
  nothing overflows the root. The 48 px strip costs 6.25% of height at 768 and
  buys a control that was previously a 1 px dashed rule. **Worth the pixels.**
- **The status detail does not overflow or truncate at 1366**: right edge 1298.4
  inside a panel ending at 1354. It WRAPS to 2 lines in the rolled-back case
  ("Travel stop at Extrude1 · 1 feature excluded") and stays on 1 line in the
  failed case ("Fillet1 failed · built to Extrude1") — so the "shares the value's
  line" design holds for the case it was written for and not for the other one,
  which is where the extra 20 px in the P1 fold measurement comes from.
- **Token discipline**: no hex literals in either new file; `TimelineStrip`'s SVG
  blade is sized from `layout.timelineHeight`, so the wedges cannot drift from
  the strip if the token changes. `partBuild.ts` derives every claim from wire
  values with request state quarantined in its own axis, exactly as advertised.

### Also measured, filed here so the next pass does not re-discover it

The **feature-tree panel's SOLVE cell is sliced at 1366x768** with 14 features:
`eval-status` is 16.5 px tall, **5 px visible, 11.5 px clipped** by the panel's
scroll box (105 px of content hidden). Same defect family as P1 — a title-block
footer inside a scroll box on a 768 px-tall screen — and the same pinning fix
covers both. Partially pre-existing (computed: the box was 598 px before the
strip and the content is 655 px, so it clipped by 57 px then and by 105 px now),
which is why it is recorded here rather than filed as a regression of UI-W1.

### Component checklist delta from this pass

| component | state |
| --- | --- |
| `TimelineStrip` — selection cue (`border-mist` on `bg-hairline`) | audited ✅ 9.38:1, ruling stands |
| `TimelineStrip` — chip rest/rolled-back border (`hairline`) | needs-work 🔴 P2-A, 1.54:1 |
| `TimelineStrip` — selected seat (`bg-hairline` on `anvil`) | needs-work 🔴 P2-B, 1.41:1 |
| `TimelineStrip` — way line solid/dashed (`etch`) | audited ✅ 3.06:1 |
| `TimelineStrip` — travel stop, drag + keys + `role="slider"` | audited ✅ (P3: no Escape-abort, no Up/Down) |
| `TimelineStrip` — travel stop focus ring | needs-work 🔴 P3, clipped to two bars |
| `TimelineStrip` — busy/held state | needs-work 🔴 P2-D, three silent gates |
| `TimelineStrip` — target sizes, tab order, reduced motion, empty/loading | audited ✅ |
| `TimelineStrip` — long build (scroll affordance, truncation) | needs-work 🔴 P3 x2 |
| `BandActionCell` — gated caption legibility | needs-work 🔴 P2-C, 2.13:1 at 9 px |
| `partBuild.ts` — one derivation feeding SOLVE/STATUS/EXPORT | audited ✅ |
| `BodyInspector` STATUS cell — qualifier layout at 1366 | audited ✅ (wraps, does not truncate) |
| `PartExportControls` / `ExportRow` — fold at 1366x768 | needs-work 🔴 P1 |
| `exportGate` — rolled-back-with-no-body reason | needs-work 🔴 P3 |
| `FeatureTreePanel` — SOLVE cell fold at 1366x768 | needs-work 🔴 P2 (pre-existing, worsened) |

### Ordered remediation plan

1. **P1** — pin the STATUS + EXPORT footer outside the Inspector's scroll box (or
   subtract `timelineHeight` from the panel clearance tokens). Verify by
   asserting `exportBottom <= scrollerBottom` at 1366x768 in BOTH the
   feature-error and travel-stop states — the partial-state notice is the one
   that is currently 100% hidden.
2. **P2-A** — move the chip's resting/rolled-back border from `hairline` to
   `etch` so the boundary and the dash clear 3:1; re-separate hover.
3. **P2-C** — replace `opacity-40` in `BandActionCell` with a disabled-foreground
   token at >= 4.5:1 and put the caption on the 10 px scale (fixes CreateStrip
   too).
4. **P2-D** — held state on the stop, `aria-disabled` on the slots, busy caption
   on TO TIP.
5. **P2-B** — add the raised-surface token and use it for every seated/selected
   row, strip included.
6. **P2 (tree)** — same pin as (1) for the SOLVE cell.
7. **P3s** — inset the stop's focus ring; edge masks + `scrollbar-width: none` on
   the way; `title` on truncated names (shared); Escape-aborts-drag and the
   missing slider keys; reorder `exportGate` so a travel stop that removes the
   body says so.

**Process note (the founder-is-the-calibrator rule).** Two of this pass's
findings — P2-A and P2-B — are cases where a source comment asserts a redundancy
that the pixels do not have ("the cue is redundant and never load-bearing
alone"; "brightest EDGE plus a lifted seat"). Both were written in good faith and
both are wrong by measurement. Adding to this checklist for every future pass:
**when a component's own comment claims two cues, measure both — a stated
redundancy is a claim, and a claim about contrast is checkable.** Same class as
the 0x0 signature element: the defect is invisible precisely because the
documentation says it is not there.

---

## 2026-08-15 — QA: the founder's "cannot assign a dimension", after `c449235`

**Verdict: the founder's complaint is HALF closed.** The verb now arms and the
editor opens, mouse-only, on the founder's exact path. But the value the user
types is then corrupted before it is committed: typed at an ordinary rhythm,
**"125" reaches the solver as 435 mm**, silently, with the glyph agreeing. A
dead end has become a wrong answer, which is the worse of the two for CAD.

**Method.** Real stack, native boot on isolated ports (gateway :8130, documents
:8131, geometry :8132), driven in real Chromium at 1600x1000 against the
**production bundle** (`vite build` + `vite preview`, not the dev server —
sibling HMR resets React state mid-typing and would have confounded every
reading). Picks are `handClick`s. The mutation control is a real build of
`c449235^` served from an isolated worktree on :5205.

### PASS — the arming fix (`c449235`) works on the founder's exact path

Draw a rectangle with the toolbar, click a side meaning "select this line"
(readout still says `nothing selected` — the rect tool owns the click), then
Constrain > Dimension > Distance: the hint reads `Click a line to dimension it.`,
the half-drawn second rectangle's live size chip is gone, and the next click on
the edge opens THAT edge's editor. Entering `60` and pressing Enter moves the
solved edge to 60.000 mm, and the value survives save + page reload + re-open
(SKETCH-1). Gated by `apps/web/e2e/sketch-dimension-typing.spec.ts`.

MUTATION (a real build of `c449235^`, same spec, verbatim):

```
Expected: "Click a line to dimension it."
Received: "Select one line to dimension."
```

and with that string assertion deleted, the same pre-fix build still fails one
step later — `expect(locator).toBeVisible() failed / element(s) not found` on
`dimension-editor`. The gate is about the behaviour, not the wording.

### P0 (DIM-1) — the value cell commits a number nobody typed

`apps/web/src/viewport/ConstraintGlyphs.tsx` renders the dimension value as a
controlled React input inside the r3f canvas via drei `<Html>`, which renders
its children into a **separate ReactDOM root** (`ReactDOM.createRoot`, re-rendered
from a `useLayoutEffect` on the parent). The `useState` draft lives in the OUTER
r3f root, so a keystroke's state update has to cross roots before the inner root
re-renders the input. Until it does, React's controlled-input restore puts the
PREFILL back. Every character typed in that window is composed against the stale
prefill, and only the last one survives: `43` + `5` = `435`.

Measured on the production build, typing `125` into a cell pre-filled `43`, keys
dispatched on a wall clock (raw CDP, so the rhythm is the one requested):

| key gap (measured in page) | field after typing |
| --- | --- |
| 171/195, 198/208, 240/270, 259/287 ms | `435` |
| 281/301, 296/316, 329/503, 349/180, 363/367 ms | `435` |
| 201/207, 253/256 ms | `125` (won the race) |
| 803/805, 920/920, 1103/1157 ms | `125` |
| 2502/2506 ms | `125` |

**10 of 12 trials at 150–250 ms/key — dead-centre human typing — committed the
wrong number**, and the corruption is not cosmetic: with the field showing `435`,
Enter sent it to the solver and the evaluate response came back with the edge at
**435 mm**. Other observed shapes: `15`, `4325`, and (at 0 ms/key) `43` unchanged.

Three properties make this worse than a slow field:

1. **It is silent.** No error, no rejection; the glyph, the field and the solved
   geometry all agree on the wrong number. The only way to notice is to re-read
   a dimension you already typed.
2. **It is not monotonic in typing speed**, so "type slower" is not a workaround
   a user could discover: keys ~155 ms apart beat the revert and survive, keys
   0.2–0.7 s apart are corrupted, keys 0.8 s+ survive again. The corrupted band
   sits exactly where ordinary typing lives.
3. **The band widens with machine load.** Under sibling-agent load, gaps of
   0.9–1.4 s still corrupted. Each keystroke costs 0.2–1.2 s of main-thread work
   (measured: two `longtask` entries per key, **zero network requests**), while
   the same page renders its frames at 17 ms median / 60 fps with the editor
   open and idle. The cost is React work per keystroke, not rasterisation and not
   a round trip.

Same defect in the same editor's **Name** cell: typing `abc` yields `c`.

**Why no existing gate caught it.** `sketch-dimension-pick.spec.ts` (shipped with
the fix) and `sketch-reopen.spec.ts` (SKETCH-1) both drive the cell with
`locator.fill()` — one DOM mutation, one input event, no window for the revert to
land in. `fill()` cannot see this defect by construction. Note also that
`locator.pressSequentially()` is only a partial escape: it awaits the renderer
between keys, so on a busy machine a requested 150 ms lands 400–1300 ms apart and
the stimulus becomes a function of load — the same assertion came back green and
red on one unchanged build. Anything asserting on per-keystroke behaviour in this
viewport needs a wall-clock driver; there is one in
`sketch-dimension-typing.spec.ts`.

Repro (30 s): open any sketch, dimension a line, type a 3-digit value at an
ordinary rhythm, press Enter, read the glyph.

### Also verified while the stack was up

- **VP-1** (`43c703c`, orbit on the middle button while sketching) — its spec had
  never been executed; all 7 tests pass against the production build.
- **SKETCH-1** (`30a9f3f`) — passes, and re-open round-trips through a page
  reload (added to the new spec: save → reload → right-click Edit → the
  dimension still reads 60).
- The builder's own `sketch-dimension-pick.spec.ts` — both tests pass.

### Not closed by this ticket

- DIM-1 above (P0) — the founder's sentence is not satisfied until this lands.
- The measure of a fixed DIM-1 is per-keystroke, not `fill()`: flip the two
  assertions named in `sketch-dimension-typing.spec.ts` and it becomes the
  positive gate.

---

## 2026-08-15 — QA: SKETCH-2, grounding a profile to the sketch frame (`5ceed6e`)

**Verdict: PASS on the founder's complaint, with four defects filed — one of
which (QA-SK2-1) means the ticket's own headline claim is not what its evidence
measures.**

Independent of the builder's `sketch-origin-constraint.spec.ts`. Real stack
(native boot, gateway :8250 / documents :8251 / geometry :8252, Vite :5351),
real Chromium, 8 new tests in `apps/web/e2e/qa-sketch-frame.spec.ts`, every
assertion mutation-verified against the pre-change behaviour.

### What is genuinely fixed

- **The founder's gesture works, and it works at every zoom.** The origin ring's
  drawn radius was measured off the canvas (brass token `#E3A64B`, sampled at
  45° so neither axis's ink can be mistaken for it): **9 px** as the sketch
  opens, **21.5 px** zoomed in 16 notches, **4 px** zoomed out. Clicking ON the
  ink at all eight compass points, plus the exact centre of the mark, selects
  the origin in all three cameras. The ink and the grab region are both derived
  in plane-mm, so the correspondence survives the dolly — that was the open
  question, since the pick tolerance is in screen px.
  - *Mutation (M2), the "naive centre-point fix" the ticket says would not have
    worked:* `Math.hypot(at) <= toleranceMm` instead of `ringRadiusMm +
    toleranceMm`. Fails at the FIRST leg — `Expected substring: "1 pt" /
    Received string: "1 ent"`. Worse than a miss: the click resolves to the X
    axis instead of the origin.
- **A rigid profile TRANSLATES.** Ground a corner, and all four corners land on
  `(0,0) (24,0) (24,16) (0,16)` — measured, not two of four (see QA-SK2-1).
  Extrudes to 1,920 mm³ / 24 × 16 × 5, so the frame's construction geometry does
  not open the wire.
- **The axes are usable targets, not just selectable things.** Two corners + the
  Y axis + `S` gives a plate symmetric about the origin (±12), and re-driving
  24 → 36 keeps it symmetric (±18) — the sentence the ticket says was not
  expressible at all. The axis materialises as pinned construction geometry with
  exactly two `fixed` pins; the X axis, never reached for, is never created.
- **TARGET-not-SUBJECT holds under attack.** All six refused verbs (`h v d r x
  e`) × all three frame members = 18 attempts, every one refused by name with
  the constraint count unchanged; `L` (perpendicular) on a drawn edge + the X
  axis is accepted and persists. The armed `dimensionPick` rung is not eaten by
  a frame click and is not lost either — the next click on a real line still
  opens its editor at 24.
- **Not just XY.** Same grounding works on XZ, and on a sketch seated on a model
  FACE (where the handle correctly reads `Face centre` and the accessible name
  carries "moves if the outline changes").
- **No regressions** in the seven specs the builder listed as NOT run: mirror,
  offset, trim/extend, fillet/chamfer, spline, visibility, construction
  geometry — 21 tests green.

### QA-SK2-1 (P1, evidence) — the fixture the ticket proves itself with is not a rectangle, and the profile it "translates" actually DEFORMS

`FLOATING_RECT` in `apps/web/e2e/sketch-origin-constraint.spec.ts` is documented
as *"rigid in SHAPE (corners tied, edges H/V, both sizes driven)"*. It carries
four coincidences, **one** `horizontal` and **one** `vertical` — where the
product's own rectangle rigidity set (`drawDimensions.ts` `rectangleRigidity`,
which rides in with the first typed dimension) is four coincidences, **two**
horizontals and **two** verticals. One H and one V short of rigid is a four-bar
linkage, not a rectangle.

Measured on that fixture, grounding `e1.start` to the origin:

```
solved: e1 (0,0)->(24,0)   e2 (24,0)->(24,16)
        e3 (24,16)->(10,24)  e4 (10,24)->(0,0)
extrude 5 mm: Volume 2,000 mm³   Extents 24 × 24 × 5
```

Two corners translated by (-10,-8); the third stayed where it was. The profile
is a sheared quadrilateral and the body is visibly wrong. The spec asserts
`e1.start` and `e2.end` — **exactly the two corners that survive** — so it
passes. With the product's real rigidity set the same gesture gives
`(0,0) (24,0) (24,16) (0,16)` and 1,920 mm³.

The kernel is not at fault: every authored constraint is satisfied. The defect
is that the commit message, the BACKLOG entry and the spec's own comments all
say *"the solver TRANSLATED the whole rectangle"*, and nothing in the repo
measures that. Fix: give the fixture `horizontal e3` + `vertical e4` and assert
all four corners. `apps/web/e2e/qa-sketch-frame.spec.ts` does both.

### QA-SK2-2 (P1, flow) — a corner already sitting ON the origin cannot be grounded to it

`datum.ts` names this case as the reason the modifier click appends the frame:
*"a corner already sitting on the origin can still be joined TO the origin — the
second Shift-click adds the datum under the one already held."* It does not.
`pickWithDatums` returns `[...drawn, ...datums]` and `toggleSelection` appends
the first candidate **not already held**, so every drawn point and edge within
tolerance is consumed first. Verbatim, on a rectangle drawn with its first
corner snapped to the origin:

```
plain click on the corner-at-origin: 1 pt · 9 applied
shift-click #1: 2 pts · 9 applied              | origin: idle
shift-click #2: 1 ent · 2 pts · 9 applied      | origin: idle
shift-click #3: 2 ents · 2 pts · 9 applied     | origin: idle
shift-click #4: 2 ents · 3 pts · 9 applied     | origin: SELECTED
shift-click #5: 3 ents · 3 pts · 9 applied     | origin: selected
shift-click #6: 4 ents · 3 pts · 9 applied     | origin: selected
press c      -> "Select two points to make coincident."
```

By the time the origin is held the selection is unusable, and there is no way to
drop what was added on the way. The user is told to do the thing they just did.
Workaround (undiscoverable, and the only one that works): select the corner,
then hold the origin through its keyboard handle — Tab to "Sketch origin",
Enter. Suggested fix: on a modifier click, order the frame FIRST when every
drawn candidate is already in the selection, or give the datum its own modifier.

### QA-SK2-3 (P2, flow, pre-existing — but SKETCH-2 puts it on the hot path) — "Finish sketch" silently drops a click

`SketchStrip.tsx` renders the finish button `disabled={saving || …}`. Every
constraint edit kicks off a live save, and the natural next action is Finish, so
a click lands in the window between actionability and React's re-render and is
delivered to a disabled button. Measured **2 failures in 10 attempts** under
load, always with the sketch fully saved (`DOF 0 · CONVERGED`, "11 applied",
button focused) and the strip simply still open after 30 s. Nothing tells the
user; they press it again and it works. It bit the builder's own spec once in
this session (`sketch-origin-constraint.spec.ts:419`) and two of mine. Fix:
don't disable across a live save (the save is already committed), or keep the
click and replay it when the save settles.

### QA-SK2-4 (P1, flow) — SNAP IS NOT A CONSTRAINT, and the tool never says so

The builder flagged this as a follow-up; it is confirmed, and it is the same
class as the founder's original report — the tool appears to have understood you
and has not. Draw a rectangle with its first corner snapped to the origin (the
snap fires, the marker reads `origin`, the DRO reads `+0.00 / +0.00`) and type a
width, so the rigidity set rides in and the plate is a real dimensioned part.
Saved: the corner is at exactly `(0,0)`, the strip reads "9 applied", and
**nothing in the model names the origin** — no `origin` entity, no constraint
referencing it.

How the user finds out: they re-drive the width 30 → 40 and the part they
anchored at zero **slides to x = −7.1716 mm**. Same plate, grounded with `c`
first, re-driven 40 → 55: the corner stays at exactly `(0,0)`.

There is no signal in between. The origin mark looks identical either way; the
readout counts the same constraints either way; there is no "under-constrained
here" mark on the corner. Minimum fix: infer a coincident when a placement point
resolves to an `origin` / `x-axis` / `y-axis` snap, exactly as the snap already
knows it did. Cheaper interim: mark a point that is coincident-with-nothing at
the origin, so the absence is visible.

### Coverage this pass did NOT reach

- **Touch.** `apps/web/playwright.config.ts` has no touch project (TOUCH-1), so
  the frame's pick affordance has never been exercised with a finger. Notable
  because the grab region is a 9 px disc at the default camera, well under any
  touch-target guideline; the zoomed-out leg measured it at **4 px**.
- **Ortho / rotated cameras.** All measurements are the parked normal-on view
  plus a dolly. Orbiting during a sketch (VP-1) was not combined with a frame
  pick.
- **The frame under undo/redo**, and deleting the coincident that grounded a
  profile (the origin entity and its pin stay in the sketch afterwards — a
  permanent, unremovable construction point; harmless but unasserted anywhere).

---

## 2026-08-17 — FOUNDER-DIRECTED AUDIT: the main file page, and where EXPORT lives

**Trigger (founder, verbatim):** *"We could shift to the UI. The main file page
looks like an after thought. … Also the button to export should not be with all
the mass properties."*

**Method.** Real stack, no containers: geometry :8032, documents :8031, gateway
:8030 on per-agent SQLite (`uiaudit-*.db`), Vite :5183. Real Chromium at
1600×1000 and 1280×800 (plus 1440×900 / 1400×800 / 1366×768 / 1280×900 for the
viewport bracket). Content seeded through the real gateway: an EMPTY account, a
ONE-part account, an 18-part + 2-folder + 2-assembly account with one part
carrying a real evaluated body, and a 120-part account. Every number below is
measured in the running app (`getBoundingClientRect`, computed styles, tab
counts), not read off the source.

### VERDICT ON THE FOUNDER'S TWO CLAIMS

**Claim 1 — "the main file page looks like an afterthought": CONFIRMED as a
read, REFUTED as a diagnosis, and the difference decides the fix.**

The surface is not unconsidered — `DocumentRegister.tsx` carries ~140 lines of
design rationale and the craft is real (see "What is actually good", below). The
defect is that it was designed as a **log book** (a ruled register you scribe
the next line into) and a working engineer needs a **file browser** (a place to
find one model out of two hundred and be inside it in two seconds). Judged as a
log book it succeeds. Judged against the Fusion Data Panel and the Onshape
document list — which is the bar — it loses on every axis those two compete on:
no preview, the identifying column is the third-narrowest, the widest column is
row verbs, and the newest work sorts last. That is what "afterthought" is
detecting. Measurements in P1-2 and P1-3.

**Claim 2 — "the button to export should not be with all the mass properties":
CONFIRMED, and the real situation is worse than the founder described. One
detail in the wording is wrong and worth correcting** — the panel is not titled
"mass properties". `BodyInspector.tsx:89` renders `propertiesEyebrow(mass)`,
which reads **PROPERTIES** and suppresses the Mass row entirely until a material
is assigned (`docs/design/materials.md` §6.1 — a deliberate anti-overclaim fix).
So the label is honest. The **information architecture** is exactly as reported:
export is the last cell of a readout stack (MATERIAL → PROPERTIES → BOUNDING BOX
→ TOPOLOGY → STATUS → **EXPORT**), styled as a readout cell, inside a panel the
user can collapse — and collapsing it deletes the only export affordance in the
product. Measurements in P1-1.

### THE TOP THREE

#### P1-1 — Part workspace — EXPORT is a child of a readout panel, and collapsing that panel removes the only way to issue a file

*Evidence:* `docs/screenshots/uiaudit-part-inspector-export-1600.png` (export as
the bottom cell of the inspector column),
`uiaudit-part-inspector-collapsed-1600.png` (inspector collapsed — no export
anywhere on screen). `apps/web/src/routes/PartPage.tsx:4665-4680`;
`AssemblyInspectorPanel.tsx:113-119`.

Measured:

- With the Inspector collapsed via its own `panel-collapse-inspector` control,
  `[data-testid="part-export-controls"]` count = **0**, visible = **false**.
  There is no File menu, no export in the top toolbar (its groups are HISTORY /
  CREATE / MODIFY / SHEET METAL / INSPECT), and no export on the breadcrumb. The
  user must know that a panel called *Inspector* is where files come from.
- **53 Tab presses** from document start to reach `part-export-step` at
  1600×1000. Export is the product's terminal action and it is the 53rd stop.
- Same defect at a second address: the assembly workspace pins its `ExportRow`
  under a SegmentedControl of **Solve / BOM / Clash** readouts
  (`AssemblyInspectorPanel.tsx:113`).
- Collapsing the panel is not an odd thing to do — mandate 3 tells the user's
  instinct to do it ("the viewport is the hero"), and the collapsed frame is
  visibly better. The UI rewards the gesture by removing a verb.

Why it costs the user: an action is not a measurement. Fusion puts export behind
the application/File menu, persistently, regardless of which side panels are
open; Onshape puts it on the document tab's own context menu, also always
present. Neither makes it a child of a properties panel. Here, a user who has
modelled a part and wants a STEP file has no document-level place to look.

**Recommended fix — the product already contains the answer.** The drawings
workspace puts export in its top command band as its own tool group:
`DrawingCommandBand.tsx:225` `<ToolGroup eyebrow="Export">` → EXPORT SVG /
EXPORT PDF / EXPORT DXF, evidenced in
`docs/screenshots/uiaudit-drawing-export-band-1600.png`. Do exactly that in
`TopToolbar` (part) and `AssemblyCommandBand` (assembly): an **EXPORT** tool
group beside INSPECT, carrying the same `exportGate` state (disabled + a
mouse-and-keyboard-reachable reason, which `PanelActionCell` already supports).
Keep the ruled strip in the inspector if you like — it is the right place for
the *notice* ("this file would be partial") — but the primary affordance belongs
in document-level chrome, where it survives a panel collapse. This is a
system-level fix: three workspaces, one `ToolGroup eyebrow="Export"` pattern
that already exists.

#### P1-2 — Parts register — the table spends its width on constants and its emphasis on destructive verbs; the identifying column is third-narrowest and hard-clips

*Evidence:* `docs/screenshots/uiaudit-parts-many-1600.png`,
`uiaudit-parts-many-1280.png`. `DocumentRegister.tsx:787-801` (`COLUMN`),
`DocumentRegisterRow.tsx:243-275`.

Measured column widths at 1280×800 (total 957 px):

| column | px | share | distinct values over the sample |
|---|---|---|---|
| # (ordinal) | 56 | 6 % | — |
| **Name** | **173** | **18 %** | the only discriminating column |
| Units | 72 | 8 % | `mm, mm, mm, mm` |
| Last worked | 144 | 15 % | mostly `NOT STARTED` |
| Rebuild | 144 | 15 % | `—` on 14 of 15 rows |
| Filed | 112 | 12 % | `2026-08-17` ×4 |
| **Actions** | **256** | **27 %** | RENAME DUPLICATE MOVE DELETE, every row |

So the widest column in a file browser is row verbs, at **1.5× the name**, and
three columns totalling **34 %** carry a constant. UNITS and FILED are
structurally constant (a document unit is a preference nobody varies per part;
FILED is same-day for everything made in a session) — REBUILD is legitimately
variable in real use, so discount that one; the other two are not defensible.
Note `DocumentRegister.tsx:38-45` diagnoses this exact failure in the *previous*
design ("two columns of the same string") — the redesign reintroduced it at a
new address.

The name is **hard-clipped with no ellipsis and no tooltip**.
`<td class="truncate">` sets `text-overflow: ellipsis`, but the link inside is
`inline-flex` (`DocumentRegisterRow.tsx:261`), which is an atomic inline box — it
gets clipped, not ellipsised. Computed `text-overflow` on the anchor: `clip`;
`title`: `null`. "Motor mount adapter plate rev C" measures 207 px in a 149 px
content box and renders as `Motor mount adapter plat` with no cue that anything
is missing and no way to recover it. Two parts whose names diverge past the cut
are indistinguishable.

There is also **no preview of any kind**. Every row is text. Fusion's Data Panel
and Onshape's document list are both thumbnail-first, because a shape is
recognised faster than a name is read, and because engineers name things badly.
This is the single largest "afterthought" signal on the page.

**Recommended fix (system-level):** (a) collapse RENAME / DUPLICATE / MOVE /
DELETE into a single row overflow menu (a `⋯` button + the existing `Flyout`
primitive) and give the reclaimed 200 px to NAME — this alone fixes the clip;
(b) fix the primitive: make the row link `inline` (or put
`overflow:hidden;text-overflow:ellipsis` on the anchor) **and** stamp `title`
with the full name, so truncation is visible and recoverable everywhere the
register is used; (c) drop UNITS from the table into the row's secondary line or
onto hover, and reclaim FILED for a thumbnail cell; (d) file a backend item for
a part thumbnail (the geometry service already tessellates — a cached PNG per
`tree_version` is the missing piece), because no amount of table tuning
substitutes for a picture.

#### P1-3 — Parts register — the return trip is backwards: oldest sorts first, the create control is below the fold, and the header/filter/sort/count scroll away

*Evidence:* `docs/screenshots/uiaudit-parts-120-1280.png`,
`uiaudit-parts-120-1280-bottom.png`, `uiaudit-parts-many-1280-scrolled.png`.
`DocumentRegister.tsx:255` (`DEFAULT_SORT`), `:1026` (`ScribeLine`),
`PartsPage.tsx:34`.

Measured, on a 120-part drawer at 1280×800:

- `aria-sort` on load: `Filed → ascending`. Order returned = creation order,
  oldest first. The page's own caption says so: *"Your parts, oldest first."*
  The thing a returning engineer wants is **what they touched last**, and it is
  the 120th row. Fusion's Data Panel and Onshape both default to
  recently-modified-first. The register even has the right column (LAST WORKED)
  and sorts by it — just not by default.
- `main.scrollHeight` = **5145 px** against `clientHeight` = 756. The only
  create control (the scribe line, ordinal 121) sits at the **bottom** of those
  5145 px. On any drawer past ~13 parts, "new part" is off-screen. The `N`
  accelerator does work and scrolls it into view, but `N` is taught by a `Kbd`
  chip that lives *on the scribe line* — i.e. it is only discoverable where it
  is not needed.
- `thead tr` computed `position: static`. Scrolling therefore loses the column
  headers **and** the sort controls (they are the headers), the FILTER field,
  the count readout and the workspace nav simultaneously. At row 104 the screen
  is six columns of unlabelled data with no way to re-sort without scrolling
  back 4 000 px.

**Recommended fix:** default sort → LAST WORKED descending (one constant,
`DEFAULT_SORT`, and update the caption); make the header rule sticky within the
register's scroll container so sort/filter/count stay addressable; move the
create affordance to a persistent position (the header rule is where it belongs
— the scribe line can stay as the in-place gesture) or float it. Optionally add
a short "Recent" band above the register — this is what Fusion's home and
Onshape's "Recently opened" do, and it is the whole answer to "get me back into
the thing I was doing".

### THE REST, RANKED

#### P1-4 — Part workspace — the ViewCube is ABSENT at every viewport height ≤ 800 px

Mandate 3a calls persistent view navigation "table stakes". It is not
persistent. Bracketed by capture:

| viewport | canvas | ViewCube |
|---|---|---|
| 1600×1000 | 1600×852 | present — `uiaudit-viewcube-1600x1000-present.png` |
| 1440×900 | 1440×752 | present — `uiaudit-viewcube-1440x900-present.png` |
| 1280×900 | 1280×752 | present — `uiaudit-viewcube-1280x900-present.png` |
| 1400×800 | 1400×652 | **absent** — `uiaudit-viewcube-1400x800-absent.png` |
| 1280×800 | 1280×652 | **absent** — `uiaudit-part-inspector-export-1280.png` |
| 1366×768 | 1366×620 | **absent** — `uiaudit-viewcube-1366x768-absent.png` |

Height-driven, not width-driven: 1280×900 has it, 1400×800 does not. The break
is between a 752 px and a 652 px canvas, i.e. exactly the two commonest laptop
frames (1280×800, 1366×768) — the responsive floor CLAUDE.md names, and the
frame `PartPage.tsx:4662` itself calls out. The ViewBar (home/fit/front/top/
right/iso) is still present, so navigation is not lost, only the cube; that is
why this is fourth and not first. `Viewport.tsx:562` `GizmoHelper` with
`margin=[96,96]`, `CUBE_MARGIN_PX = 96` — the cube's own footprint constant
(`CUBE_FOOTPRINT_PX = 120`) suggests 96 + 120/2 exceeds something at short
canvas heights. Needs a builder to root-cause; a regression test asserting cube
ink at 1280×800 should ship with the fix. NB a naive canvas `drawImage` readback
does NOT discriminate here (it returned ~350 near-white pixels at every width,
present or absent) — assert on the page screenshot, not the WebGL buffer.

#### P2-1 — Parts register — the row lights up on hover but only the name text is clickable, and OPEN is the only verb without a label

`<tr class="… hover:bg-carbide">` (`DocumentRegisterRow.tsx:236`) highlights the
whole 957 px row; the only navigable element is the anchor, measured at **84 px**
wide for "Bracket plate". The other ~870 px of a row that visibly responds to
the pointer do nothing. Meanwhile FOLDER rows carry an explicit **OPEN** verb
and document rows do not — so on the same table, the primary action is
unlabelled while three secondary actions and one destructive one are labelled at
equal weight. That is inverted priority, and it is the founder's "afterthought"
in miniature. Fix: make the row cell (or the row) the open target with the
anchor still the accessible name, and put DELETE behind the overflow menu from
P1-2.

#### P2-2 — Parts register (empty) — first impression is a form in a void

`uiaudit-parts-empty-1600.png`: at 1600×1000 the register occupies x≈320–1280
(60 % of the frame; **40 % is empty grid**), and inside it a 4-line invitation
sits above ~850 px of blank ruled lines. There is no sample part, no import
path, no statement of what Loft does. Onshape ships sample documents for exactly
this moment. Fix: give the empty state something to *do* besides type — one
"open a sample part" that seeds a real 3-feature tree is the cheapest retention
lever on the page — and let the register use the full frame rather than a
`max-w-5xl` marketing column (`PartsPage.tsx:79`).

#### P2-3 — Parts register — the FILTER field is rendered at n = 1

`uiaudit-parts-one-1280.png`: a single part, and the header still carries FILTER
+ its `/` chip. It is not *dead* (it works), but a filter over one row is chrome,
and mandate 3c's spirit is that a control should be able to justify itself.
Suggest a threshold (say ≥ 8 rows) — the `/` accelerator can stay live regardless.

#### P3-1 — Parts register — FILTER label and input sit on different baselines

Visible in every register shot: the header is `items-baseline`, but the input
carries `pb-0.5` + a bottom border, so the value "Name contains…" rides above
the tracked FILTER label. One-line primitive fix.

#### P3-2 — Register — 10 px row verbs; 24 px targets meet the AA floor and nothing more

Row verbs compute to `font-size: 10px` uppercase with 0.14em tracking, hit
targets 53×24 / 76×24 / 38×24 / 53×24. That satisfies WCAG 2.5.8 (24 px minimum)
exactly, with no margin, and is well under a comfortable touch target. Relevant
because `playwright.config.ts` still has no touch project (TOUCH-1), so no
tablet-class pass has ever run over this table. Largely moot if P1-2's overflow
menu lands.

#### P3-3 — Scale watch — 120 rows render in full, no virtualisation, no pagination

Measured: 120 documents → 120 `<tr>`, `scrollHeight` 5145 px, no perceptible
lag. Correct today, and correctly documented (`DocumentRegister.tsx:258-267`
notes the whole drawer is on the wire so "4 of 12" can mean it). Flagged only so
the pairing is remembered: the day the list endpoint paginates, the filter must
move server-side in the same change.

### What is actually good (do not regress these while fixing the above)

- **Contrast and focus pass cleanly.** Every sampled register token measures
  **7.18:1** or better on `anvil` (column headers, row verbs, "Not started",
  count) and the name link 13.21:1. The focus ring is an unmistakable brass
  outline — `uiaudit-parts-focus-1600.png`.
- **The scribe line is genuinely distinctive.** A create control that is the
  *next numbered line of the register*, carrying the next ordinal, is the one
  thing on this page no template would produce. Keep it; just stop making it the
  only way to create (P1-3).
- **Filter semantics are honest and better than the incumbents'.** It searches
  the whole drawer including inside folders, each hit states where it lives
  (`uiaudit-parts-filtered-1600.png`), and the count becomes a fraction ("2 of
  18 parts") so an empty result reads as "nothing matched" rather than "my work
  is gone". `uiaudit-parts-no-matches-1600.png` names the query and offers the
  one control that fixes it.
- **Sort-as-column-header** adds no chrome and carries real `aria-sort`.
- **Folders-as-dividers** with server-supplied counts, and a breadcrumb that IS
  the title — no second navigation strip.
- **The part workspace itself reads as a tool.** Studio matcap, grid to the
  horizon, atmospheric background, honest PROPERTIES/STATUS cells. The founder's
  complaint is about the file page and the export placement, not this.

### Coverage this pass did NOT reach

- Drawings register (only the drawings *workspace* command band was captured).
- Touch/tablet viewports (no touch project exists — TOUCH-1).
- `prefers-reduced-motion` on the register was launched but the register carries
  only `duration-fast` colour transitions, so there was nothing to observe; the
  viewport's reduced-motion path was not re-exercised this pass.
- Long-content in a FOLDER name, and a drawer with >5 folders.

### Running component checklist (delta from this pass)

- 🔴 `DocumentRegister` / `DocumentRegisterRow` — P1-2, P1-3, P2-1, P2-3, P3-1, P3-2
- 🔴 `PartsPage` / `AssembliesPage` / `DrawingsPage` shell — P2-2 (max-w-5xl column, empty state)
- 🔴 `TopToolbar` / `AssemblyCommandBand` — P1-1 (no EXPORT group; `DrawingCommandBand` has one)
- 🔴 `Viewport` / `ReferenceCube` — P1-4 (absent ≤ 800 px viewport height)
- ✅ `ExportRow` — the strip itself is correct (honest gate, reason on the cell,
  `aria-live` status); only its PLACEMENT is the defect
- ✅ `BodyInspector` — the readouts and the PROPERTIES/MASS honesty are right
- ✅ Register focus / contrast / filter / empty-result states
