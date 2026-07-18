# Changelog archive

Full-detail changelog entries pruned from `docs/BACKLOG.md`'s "Changelog"
section each grooming pass (one-line-per-entry there; detail preserved
here). Newest first. Evidence for shipped items also lives in the Done
archive (`BACKLOG.md`) and per-item commits.

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
