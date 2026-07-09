# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 0 — Foundation.**

Source of truth for "what phase are we in." Every commit that ships an item
ticks it here (and on `docs/BACKLOG.md`) in the same commit — see CLAUDE.md.

## Phase 0 — Foundation 🚧

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
- ⬜ Service skeletons: `gateway`, `geometry`, `documents` — each boots, serves
      `/healthz` + `/readyz`, has a Dockerfile; `docker compose up` brings up
      db + redis + minio + services + web
- ⬜ Contract pipeline: OpenAPI generated from pydantic → committed to
      `packages/contracts` → `packages/ts-client` generated; CI drift check
- ⬜ Web shell: Vite + React + TS app with router, layout, and an r3f viewport
      rendering a server-tessellated cube from the geometry service (proves
      the whole pipe: HTTP → queue → OCCT → GLB → viewport)
- ⬜ CI: lint + typecheck + unit tests (path-filtered per package) + compose
      config validation
- ⬜ Geometry golden-suite harness (first golden model: the cube) + STEP
      round-trip test
- ⬜ Community surface: README (truth-only), CONTRIBUTING, SECURITY, issue
      templates
- ⬜ Watchdog: stall-recovery routine armed per `docs/AUTONOMOUS-LOOP.md` §1.4

## Phase 1 — MVP: sketch → extrude → export ⬜

The thinnest vertical slice a working engineer can feel:

- ⬜ Auth: email/password, JWT via gateway; single-workspace
- ⬜ Documents: create/list parts; parametric feature tree persisted (JSONB
      params + ordered tree)
- ⬜ Sketcher v1: plane selection, line/rect/circle/arc, dimensional +
      geometric constraints (planegcs behind `SketchSolver` interface)
- ⬜ Features v1: extrude (add/cut), fillet, chamfer; feature re-evaluation on
      param edit; error surfacing when a feature fails to rebuild
- ⬜ Viewport v1: orbit/pan/zoom, face/edge picking, section-free display of
      tessellated body, feature-tree panel with edit/rollback
- ⬜ Export: STEP + STL download
- ⬜ Golden models: 5 reference parts covering every shipped feature
- ⬜ E2E: Playwright — login → sketch → extrude → edit param → export, desktop
      and touch viewport smoke

## Phase 2 — Parametric core ⬜

- ⬜ Full sketcher: splines, mirror/pattern, construction geometry, DOF
      display, over-constraint diagnostics
- ⬜ Features: revolve, sweep, loft, shell, draft, holes, linear/circular
      patterns, boolean between bodies, datum planes/axes
- ⬜ Named references that survive rebuilds (topological naming strategy —
      the hard CAD problem; design doc required before build)
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
