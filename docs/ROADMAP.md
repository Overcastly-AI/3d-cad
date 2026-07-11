# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 2 — Parametric core.** Phase 1 is complete: the
login → sketch → extrude → edit-param → export loop is proven end-to-end in a
real browser against the real stack by the `full-flow` exit-gate e2e (commit
ff6b226, 2026-07-11). Phase 2 widens the sketch constraint vocabulary (the
Sketching scorecard row's named gap) and adds core modeling features (revolve
first), gated by a topological-naming design doc where features need stable
face/edge references. See `docs/BACKLOG.md` Ready queue.

Source of truth for "what phase are we in." Every commit that ships an item
ticks it here (and on `docs/BACKLOG.md`) in the same commit — see CLAUDE.md.

## Phase 0 — Foundation ✅

All buildable items shipped through commit 322a988 (including the full
code-review fix batch). Two items below stay ⬜ because they are
**environment-blocked, not build-blocked** — neither can be attempted in this
sandbox regardless of code state, so they do not gate the phase advance; they
carry forward as blocked board items.

- ✅ Loop blueprint from Next-Lane review (`docs/AUTONOMOUS-LOOP.md`)
- ✅ Direction docs: VISION, RESEARCH, ROADMAP, BACKLOG
- ✅ `CLAUDE.md` constitution + `.claude/` agent org (agents, skills, workflows)
- ✅ Design mandate: `frontend-design` skill vendored (Apache-2.0) + standing
      UI/UX directive in CLAUDE.md/VISION.md, wired into frontend agents
- ✅ Monorepo scaffold: uv + pnpm workspaces (incl. `@loft/design`
      placeholder), `justfile`, ruff/pyright/eslint/prettier configs —
      `just lint` + `just test` green
- ✅ `packages/py-kit` service bootstrap (config, JSON logs, health/readiness,
      error envelope, arq queue client), unit tested
- ✅ Service skeletons + compose: `gateway`, `geometry`, `documents` boot on
      py-kit, serve `/healthz` + `/readyz`; one parameterized service
      Dockerfile + compose stack (db/redis/minio + services, healthy-gated)
      authored and config-validated; smoke + per-instance dev scripts;
      probes verified against bare-uvicorn boots (web joins compose with the
      web-shell item)
- ⬜ Verify full `docker compose up` on a Docker-capable host (this sandbox
      has no docker daemon — images and stack runtime are unproven).
      **Environment-blocked**, does not gate phase advances; first
      Docker-capable session picks it up
- ✅ Contract pipeline: OpenAPI generated from pydantic → committed to
      `packages/contracts` → `packages/ts-client` generated (`just gen`);
      drift check ready as `just gen-check` (CI wiring lands with the CI
      bullet below)
- ✅ Web shell: Vite + React + TS app with router, layout, and an r3f viewport
      rendering a server-tessellated cube from the geometry service via the
      gateway, with the `packages/design` token system (design-mandate debut:
      title-block inspector, one palette across DOM + WebGL) and live
      parametric dimension editing; proven end-to-end in Chromium with
      screenshots (`docs/screenshots/`). Honest note: the queue leg is still
      sync-inline — the pipe today is HTTP → gateway → OCCT → GLB → viewport;
      arq/redis queue runtime lands with the queue/storage items
- ✅ CI: lint + typecheck + unit tests + contract drift check + compose
      config validation as GitHub Actions (`.github/workflows/ci.yml`, four
      parallel jobs, uv cache keyed on uv.lock); workflow authored + every
      job's commands verified passing locally — first hosted run occurs on
      push (per-package path filtering deferred until job times warrant)
- ✅ Geometry golden-suite harness (first golden model: the cube) + STEP
      round-trip test — data-driven runner over `services/geometry/goldens/`
      (documented per-model tolerances, exact topology/mesh counts,
      byte-level determinism incl. interpreter-restart), STEP round-trip at
      0.0 measured deviation; evidence + gap list in `docs/GEOMETRY-QA.md`
      (`just e2e` wired 2026-07-10: `scripts/e2e.sh` runs geometry gates +
      Playwright, booting/reusing services itself; CI e2e job deferred)
- ✅ Community surface: README (truth-only — hero screenshot, honest status,
      verified quickstart, CI badge), CONTRIBUTING, SECURITY,
      CODE_OF_CONDUCT, bug/feature issue templates + PR template
- ⬜ Watchdog: stall-recovery routine armed per `docs/AUTONOMOUS-LOOP.md` §1.4
      (blocked on the loop actually running unattended — armed when batch
      chaining starts; does not gate phase advances)

## Phase 1 — MVP: sketch → extrude → export ✅

Complete 2026-07-11 — the `full-flow` Playwright e2e (commit ff6b226) proves
the whole vertical slice end-to-end in a real browser against the real stack:
register → create part → sketch → extrude → edit param → export STEP/STL.
Full evidence lives in `CHANGELOG.md` and `docs/GEOMETRY-QA.md`; one line per
item below.

- ✅ Auth — email/password JWT via gateway, single-workspace
- ✅ Documents — parts CRUD + feature-tree persistence (create/list/get/
      delete, reorder, rollback-bar, versioned param envelopes)
- ✅ Sketcher v1 — plane pick, line/rect/circle/arc, 6 constraint kinds
      (coincident/horizontal/vertical/distance/radius/fixed) with
      keyboard-first verbs, DOF readout, conflict diagnostics
- ✅ Features v1 — extrude (add/cut), fillet, chamfer; per-feature rebuild
      errors surfaced legibly in the tree panel under the strict-prefix rule
- ✅ Viewport v1 — orbit/pan/zoom, evaluated-body render, feature-tree panel
      with select/edit/rollback (face/edge picking deferred — see Phase 2,
      gated on the topological-naming design doc)
- ✅ Export — STEP + STL, from bare shapes and from evaluated feature trees
- ✅ Golden models — 5 reference parts (`box-10x20x30`, `cylinder-r10-h25`,
      `sketch-extrude-40x25x10`, `fillet-plate-r5`, `chamfer-plate-d5`);
      every shipped feature is golden-covered at 1e-9, STEP round-trips
      0.0–1.26e-10
- ✅ E2E — `full-flow.spec.ts`: desktop + 1280×800 + a touch-viewport smoke

## Phase 2 — Parametric core 🚧

- ⬜ Topological naming strategy — design doc first (the hard CAD problem;
      gates any feature/UI that lets a user pick and persist a reference to
      a specific face/edge — face/edge picking, hole placement, pattern
      seeds)
- ⬜ Full sketcher: tangent/perpendicular/parallel (✅ shipped: schema+planegcs
      solver 3a + P/L/T keyboard verbs & ∥/⊥/T glyphs 3b — 3 of the 6 new
      constraint kinds done)/equal/symmetric/concentric (✅ shipped:
      schema+planegcs solver 4a + E/S/O keyboard verbs & =/⟷/◎ glyphs 4b —
      the remaining 3). **All 6 new constraint kinds are now done** (H/V/D/R/X/C
      base + P/L/T + E/S/O); the Sketching scorecard row is a re-score
      candidate — vision-steward to reassess.
      constraints (the Sketching scorecard row's named gap),
      construction geometry (✅ shipped: schema+solver+profile-exclusion +
      N-verb UI toggle with dashed/muted rendering), trim/extend,
      mirror/pattern, splines, over-constraint diagnostics
- ⬜ Features: revolve (✅ shipped — 5a kernel+schema+golden
      `revolve-annulus-r10-20-h15` + 5b authoring UI: title-block editor with
      line-entity axis pick & brass angle handle, live edit, tree errors).
      **4 body-affecting features now (extrude+revolve+fillet+chamfer)** — the
      Part-modeling scorecard row is a re-score candidate (vision-steward to
      reassess; still predicate-only edge selection, no hole/pattern/shell/
      draft). Next: sweep, loft, shell, draft, holes, linear/circular
      patterns, boolean between bodies, datum planes/axes
- ⬜ Design system: grouped-icon toolbar + flyouts (✅ shipped — icon layer
      for the growing tool count: `ToolButton`/`ToolGroup`/`Flyout`/`Kbd` +
      hand-drawn scribed CAD icon set in `packages/design`; sketch tool +
      constraint toolbar (Geometric/Dimensional/Relational flyouts) and the
      feature Create toolbar converted; every keyboard shortcut preserved as a
      tooltip accelerator; full e2e green. Doc: `docs/design/toolbar-system.md`).
      Next: convert the remaining text-idiom surfaces (DRO, editor toggles,
      export) + a Modify group as fillet/chamfer/sweep land
- ⬜ Measurement tools, mass properties panel, units system
- ⬜ Performance benchmark suite with budgets in CI
- ⬜ Undo/redo across feature operations

## Phase 3 — Assemblies, versioning, collaboration ⬜

- ⬜ Assemblies: instances, mates/joints, BOM
- ⬜ Document versioning: history, branch, merge-view (design doc first)
- ⬜ Realtime presence + multi-user editing via gateway WebSocket
- ⬜ Helm chart + Kustomize; HA topology guide

## Phase 4 — Interop & drawings ⬜

- ⬜ STEP/IGES import with healing report
- ⬜ 2D drawings: views from model, dimensions, PDF/DXF export
- ⬜ 3MF/OBJ export; mesh quality controls

## Phase 5 — Agent-native & extensibility ⬜

- ⬜ Public Python scripting API (same code path as the UI)
- ⬜ MCP server: create/edit sketches and features, query mass properties,
      export — the agent-native surface (`docs/VISION.md` advantage #4)
- ⬜ Plugin/extension mechanism
- ⬜ SSO/OIDC for teams
