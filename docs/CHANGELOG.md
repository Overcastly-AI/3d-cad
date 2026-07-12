# Changelog archive

Full-detail changelog entries pruned from `docs/BACKLOG.md`'s "Changelog"
section each grooming pass (one-line-per-entry there; detail preserved
here). Newest first. Evidence for shipped items also lives in the Done
archive (`BACKLOG.md`) and per-item commits.

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
