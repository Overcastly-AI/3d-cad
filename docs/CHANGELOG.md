# Changelog archive

Full-detail changelog entries pruned from `docs/BACKLOG.md`'s "Changelog"
section each grooming pass (one-line-per-entry there; detail preserved
here). Newest first. Evidence for shipped items also lives in the Done
archive (`BACKLOG.md`) and per-item commits.

## 2026-08-08 to 2026-08-11 (CI-4 fixes, SEL-4/6/6b)

- 2026-08-11 — CI-4 review fix (backend-builder): `--fail-on-flaky` guard
  matched its own text; flag literal now assembled in pieces, 3 probes, 4
  mutations verified (`aea990a`).
- 2026-08-11 — CI-4 frontend slice (frontend-builder): `waitForRenders`
  counts r3f renders, throws with count achieved; `sketch-visibility` ink=0
  reproduced 5/10 locally, an AA phase lottery not a regression (SPEC-4).
- 2026-08-11 — SEL-6/6b independent QA verdict: PASS (qa-tester) — occluded
  plate 94.8% with occluder hidden (was 8.5%), names near face; 5 mutations
  red.
- 2026-08-08 — SEL-6b (frontend-builder): `hiddenPicks.ts` withholds a
  hidden body's edges/faces/snap points; 24 edge marks -> 12, 12 face -> 6.
- 2026-08-08 — SEL-6 (frontend-builder): `pickRaycast.ts` filters hidden
  triangles; shell reachability with wall hidden 7.4% -> 96.3%.
- 2026-08-08 — SEL-4 independent QA verdict: PASS (qa-tester) — 25 e2e green,
  10 checks the shipped gate didn't express (draft, refusals, recede, touch).
- 2026-08-08 — SEL-4 review follow-up (frontend-builder): hidden body stops
  occluding edge band; mate picks 8.9% -> ≥50%; one owner for mate hover.
- 2026-08-08 — SEL-4 (5/5) dense-hole gate (frontend-builder): anisotropy not
  area for edges, mutation-verified on all three conversions.
- 2026-08-08 — SEL-4 (4/5) drill anywhere on the face (frontend-builder):
  free placement by raycast + plane projection.
- 2026-08-08 — SEL-4 (3/5) shell/draft/mates address geometry
  (frontend-builder): surface raycast + edge band; shell reachability
  1.7% -> 95.6%.
- 2026-08-08 — SEL-4 (2/5) fillet/chamfer/measure pick the edge
  (frontend-builder): 24px screen-space corridor with occlusion test.
- 2026-08-08 — SEL-4 (1/5) one pick hit-test, shared (frontend-builder):
  `PickSurface`/`FacePatch`/`useViewportPickStamp`/`edgeBand` extracted.

## 2026-07-19 to 2026-07-20 (sheet-metal v2 + corner relief + hem v1 +
STEP hardening + WB-64/TB-1 dogfooding)

- **Sheet-metal CLOSED HEM (kernel-architect):** first-class `sheet_metal_hem`
  feature — a fixed 180° fold reusing `build_edge_flange` + the shipped unfold
  verbatim. Finding: the near-flat fold cannot self-intersect (return sits
  ~2·radius above base), so it's one clean valid solid, no guard. Golden
  `closed-hem-plate`; existing goldens byte-unchanged. Open/teardrop/rolled +
  a Hem UI deferred.
- **Sheet-metal CORNER RELIEF v1 (kernel-architect):** reconciled + finished
  container-restart-stranded work (`_Rect` defined after first use → import
  `NameError`; 12 ruff errors — cleared). `apply_corner_relief` cuts the
  rectangular 3D notch; `unfold_sheet_metal(reliefs=...)` develops the
  relieved depth-1 tray (reentrant notch, area conservation,
  byte-deterministic). Golden `corner-tray-relieved-unfold` + 12 tests; all
  depth-1/2 goldens byte-unchanged.
- **Sheet-metal depth-≥2 bend-TREE unfold FEATURE (kernel-architect):** spike
  graduated into `unfold_sheet_metal`; depth-2 (box corner / return / Z) now
  unfolds to ONE union outline, self-overlap → typed `UnfoldOverlapError`.
  Depth-1 goldens byte-identical; new `bend-chain-{corner,parallel}-unfold`;
  spike retired.
- **Sheet-metal depth-≥2 bend-chain unfold SPIKE (kernel-architect):**
  VERDICT **TRACTABLE, no wall.** Recursive-compositional tree walk unfolds a
  box corner (flange off a flange) — each child placed in its parent's
  already-flattened frame; BA-strip residual ~3e-15, isometry residual 0.0,
  exact area conservation, byte-deterministic. Isolated `_spike_bend_chain.py`
  + 2 goldens (perp corner + parallel chain); shipped depth-1 unfold
  byte-unchanged. Follow-on feature slices named in design §4.3.
- **Sheet-metal depth-2 no-crash + N=4 pan golden (kernel-architect):**
  code-review follow-up on the non-parallel unfold. Author-reachable depth-2
  bodies (flange off a flange) now raise a UNIFORM typed `UnfoldStarError`
  before the layout — the perpendicular box corner no longer leaks a raw
  kernel `Standard_ConstructionError`; plus-pattern assembler guards its
  full-width closed-loop assumption; `BendLine.flat_start/end` 2D-frame
  semantics documented; new `pan-four-flange-perp-unfold` golden. Parallel
  goldens byte-identical.
- **Sheet metal v2 #1 — non-parallel bend stars (kernel-architect):** spike
  proved the 2D plus/cross layout tractable (shared corners included —
  disjoint arms, exactly-additive volume). `unfold_sheet_metal` branches
  parallel (byte-identical 1D strip) vs non-parallel (2D tray); new
  `corner-tray-perp-unfold` golden + narrowed `UnfoldStarError`. Full
  geometry suite green.
- **STEP parse-timeout hardened (kernel-architect):** wall-clock bound →
  CPU-time ceiling (`RLIMIT_CPU`, default 20 s) + wall-clock liveness backstop
  (default 60 s); kills the CPU-contention false-fire flake while preserving
  the DoS guard. Full geometry suite green; flaky tests 8× clean under 2× CPU
  oversubscription. No contract change.
- **Groom + restock (backlog-groomer, 2026-07-19):** reconciled BACKLOG +
  ROADMAP against `36dc3d9..a6a5814` (six converged pillars: Assemblies,
  Drawings+export, Multi-body, Units, Undo/redo, Sheet metal); archived ~950
  lines of shipped items to one-liners, backfilled two missing CHANGELOG.md
  batches, fixed 5 stale ROADMAP phase/sub-item markers, closed two stale
  unchecked duplicate items (already shipped) and two stale Next items
  superseded by shipped pillars. Restocked Ready with 9 items.
- **Founder dogfooding pass #2 — TB-1 site toolbox (all queued scenarios, one
  assembly, 2026-07-20):** tray (4 walls + 2 hems + 4 reliefs — first
  coexistence, 12 features OK), pattern ×4 (exact to 0.01 mm³), spline-loft
  grip, 8-instance assembly + BOM, authz probes clean. ONE new kernel finding:
  hem-on-flange-top can't flat-pattern (typed reject, filed P2).
- **Drawings auto-layout FIT-SCALE (from WB-64 findings, 2026-07-20):**
  `fitScale` picks the largest standard scale fitting the quadrant cells
  (user's pick = ceiling); 6 unit cases, drawings e2e green. Sheet-size
  select + flat-pattern fit remain (P3). Retro items filed: Drawings parity
  campaign (P1), dead-capability sweep, recurring dogfooding gate, threads.
- **Founder dogfooding — WB-64 64 oz bottle (full product pass, 2026-07-20):**
  bottle/cap/assembly/GA modeled + verified in-app (cavity kernel-vs-analytic
  Δ=2 mm³ in 2.11 L); 3 drawing findings filed (Ready), no geometry defects.

## 2026-07-12 (post product+engineering audit batch)

- **Multi-loop closed profiles → holes shipped** (`a36e436`, product audit's
  #1 gap). `build_profile_face` (kernel/extrude.py, shared by
  extrude/revolve/sweep/loft) classifies the largest-area loop as the outer
  boundary, the rest as interior holes → `Face(outer, inner_wires)`; no
  topological naming needed. v1: one outer boundary + disjoint strictly
  interior holes; disjoint/crossing/overlapping/nested loops →
  `profile_unsupported`, open loop → `profile_not_closed`. Golden
  `sketch-extrude-plate-2holes-40x25x10` (analytic V, 8 faces, STEP
  round-trip + restart determinism). [kernel-architect]
- **F3 doc-defect fixed** (`c9abf7e`) — `loft.py`'s module note still said
  offset planes were unauthorable after `df308e4` landed them; synced.
  [kernel-architect]
- **#8b Loft authoring UI shipped.** Ordered section-stack picker (≥2 sketch
  sections, add/remove/reorder — order is the blend sequence) with a "blend
  spine" signature, Add/Cut, `L` accelerator, honest v1 note; DRY
  `LoftParamsV1` from `@loft/ts-client`. e2e (real stack): two parallel
  circles (XY + XY+30 via "+ Offset plane") → a rendered frustum in the tree;
  submit guard on incomplete stacks. Closes #8. [frontend-builder]
- **#2b offset/datum-plane picker UI shipped.** One-click origin planes
  preserved; inline "+ Offset plane" + standalone Datum tool create a
  `datum` feature the sketch seats on via `FeatureRef`. `plane.ts`
  generalized to a placed `PlaneBasis` (one plane-math source, DOM+WebGL).
  e2e proof: XY+30 sketch→extrude → body bbox z≈30..40. #8b loft UI now
  fully unblocked. [frontend-builder]
- **Offset/datum planes — BACKEND shipped.** `DatumFeature` in the Feature
  union + registry; sketch-on-datum via the widened `FeatureRef` plane slot;
  `resolve_sketch_plane` DRY funnel → resolved `Plane`. Goldens: offset
  extrude + the two-parallel-circles→cylinder loft. Ready #2 backend done;
  #8b loft UI unblocked; #2b plane-picker UI is follow-up. [kernel-architect]
- **Datum-planes design note landed** (`docs/design/datum-planes.md`):
  datum-plane-as-feature (vs inline spec); v1 = offset-from-origin-datum by
  signed distance; additive backward-compat (no `param_version` bump). Ticks
  Ready #1; unblocks #2 impl + #8b loft UI. [kernel-architect]
- **Groomed after the sketch-cluster + sweep/loft-backend batch.** Archived
  8 shipped items (session-tool cluster, sweep, loft backend); restocked
  Ready with offset/datum planes (design note + implementation, ranked top —
  unblocks #8b loft UI), face/edge picking, and 3 sketch-polish items; #8b
  explicitly marked blocked. [backlog-groomer]

## 2026-07-12

- **Loft (#8) BACKEND shipped.** `LoftFeature`/`LoftParamsV1` (`profiles:
  FeatureRef[]` min 2 + add/cut), `build_loft_section`/`loft_sections` ruled
  `make_loft`, evaluate-tree handler. Sections = closed wire OR single apex
  point (loft-to-a-point). Golden `loft-pyramid-sq20-h30` (analytic pyramid
  4000 mm³) through every gate. Apex support unblocks an analytic golden
  (parallel offset sections need offset datum planes). #8b (UI) queued,
  later marked blocked on offset/datum planes. [kernel-architect]
- **Sketch fillet/chamfer (#5) BACKEND shipped.** `POST /api/v1/
  sketch/{fillet,chamfer}` (gateway-proxied): exact closed-form corner
  round/bevel — both lines trimmed to their tangent/setback points, arc/line
  bridge appended (fresh `f"{a}.{n}"` id). v1 line-line only (line-arc/
  arc-arc deferred). Also hardened `_mirror_entity` dispatch with
  `assert_never`. #5b (UI) queued. [kernel-architect]
- **Sketch mirror (#4) BACKEND shipped.** `POST /api/v1/sketch/mirror`
  (gateway-proxied): exact analytic reflection of point/line/circle/arc
  about a line-entity-id OR two-point axis; arc CCW-swap preserves the
  invariant. #4b (UI) queued. [kernel-architect]
- **Ready #1 (Fillet/Chamfer authoring UI) shipped** + reopened #6 P1
  fixed: measure pick-marks now hit-test by real click/tap (edge marks at
  true midpoint, vertex z-priority, visible reticle nodes). [frontend-builder]
- **Groomed for Phase 2 restock.** Ready batch 1 (7 items: topological
  naming, construction geometry, 6-constraint vocabulary, revolve,
  measurement, pattern) archived; older changelog entries moved to
  `CHANGELOG.md`. New 10-item Ready queue from `docs/COMPETITIVE.md`'s first
  discovery pass + a code-inspection finding (Fillet/Chamfer buttons wired
  but never connected — `PartPage` never passes `onFillet`/`onChamfer`).
  [backlog-groomer]
