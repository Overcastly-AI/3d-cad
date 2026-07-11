# Roadmap

Status legend: ✅ done · 🚧 in progress · ⬜ planned

**Current focus: Phase 1 — MVP: sketch → extrude → export.**

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
      **Environment-blocked**, does not gate the Phase 1 advance; first
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
      chaining starts; does not gate the Phase 1 advance)

## Phase 1 — MVP: sketch → extrude → export 🚧

The thinnest vertical slice a working engineer can feel:

- ✅ Auth: email/password, JWT via gateway; single-workspace (backend
      shipped 2026-07-10: argon2id + HS256 register/login/me under
      `/api/v1/auth/*`, users via alembic `0001_users`, fail-fast JWT_SECRET
      posture, hard postgres readiness. Web sign-in shipped 2026-07-10:
      drawing-sheet sign-in/register, localStorage session, global
      invalid-token expiry → quiet notice; e2e-verified
      register→login→refresh→logout, 15/15 Playwright green)
- 🚧 Documents: create/list parts; parametric feature tree persisted (JSONB
      params + ordered tree) (parts CRUD shipped 2026-07-10: owner-scoped
      create/list/get/delete via alembic `0001_parts` + auth-protected
      gateway aggregation, db/alembic plumbing shared through py-kit.
      Feature-tree persistence shipped 2026-07-11 per
      docs/design/feature-tree.md §1-3/§5: alembic `0002_feature_tree`
      [deferred constraints, composite same-part FKs], feature
      CRUD/reorder/rollback-bar API with reference rules,
      409-with-dependents, 422-stale-version, versioned param envelopes +
      upcast registry in py-kit, gateway aggregation; geometry evaluate
      slice pending → BACKLOG #2)
- 🚧 Sketcher v1: plane selection, line/rect/circle/arc, dimensional +
      geometric constraints (planegcs behind `SketchSolver` interface —
      solver layer shipped 2026-07-10: protocol + planegcs 0.8.0 backend,
      LGPL-2.1 verified, benchmark rectangle at 0.0 deviation,
      bitwise-deterministic; RESEARCH §2. Sketch persistence/API/UI pending)
- ⬜ Features v1: extrude (add/cut), fillet, chamfer; feature re-evaluation on
      param edit; error surfacing when a feature fails to rebuild
- ⬜ Viewport v1: orbit/pan/zoom, face/edge picking, section-free display of
      tessellated body, feature-tree panel with edit/rollback
- ✅ Export: STEP + STL download (shipped 2026-07-10 — byte-deterministic
      STEP/STL geometry endpoint with round-trip gates, gateway proxy, and
      title-block export controls in the web app; QA'd in a real browser:
      Playwright downloads `box.step`/`box.stl` through the full stack and
      asserts file contents)
- 🚧 Golden models: 5 reference parts covering every shipped feature (2 of
      5: `box-10x20x30`, `cylinder-r10-h25` — first curved golden shipped
      2026-07-10 with a measured 1e-9 curved-GProp tolerance, seam-edge
      topology, and a curved STEP round-trip baseline; docs/GEOMETRY-QA.md)
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
