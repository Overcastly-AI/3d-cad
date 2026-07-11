# Changelog

All notable changes to this project are documented here. This file is updated
in the same commit as each shipped feature, fix, or infrastructure change.

Format: dates are commit dates (UTC); sections group related work from the same
wave.

## [Phase 0: Foundation] — 2026-07-09 to 2026-07-10

### Direction & governance (2026-07-09)

- **docs: compile autonomous build-loop blueprint from Next-Lane review**
  — `docs/AUTONOMOUS-LOOP.md`: the orchestrator protocol, orchestration
  procedures, gate definitions, and retry/fallback logic inherited from
  Next-Lane, adapted for this team's specialist-agent architecture.

- **feat: Phase 0 direction layer + tailored AI agent org**
  — `docs/VISION.md`: four structural advantages, daily-driver scorecard,
  phase gates. `.claude/agents/`, `.claude/workflows/`, and
  `.claude/README.md`: org chart (builders, independent QA, direction roles),
  workflow dispatch rules, briefing templates.

- **feat: make frontend design a standing founder priority**
  — Architectural decision: design is first-class, not polish. `frontend-design`
  skill vendored (Anthropic, Apache-2.0); mandatory for all UI work.

- **docs: adopt packages/design as the design-system home (founder decision)**
  — Design tokens, primitives, and fonts live in a **source-only** pnpm
  workspace package (not inside `apps/web`). Rationale: one palette for DOM
  and WebGL; greppable boundary for design-mandate enforcement; brand cohesion
  for future consumers (docs site, landing page). Updated RESEARCH.md §5,
  CLAUDE.md, agent briefs.

### Monorepo & service foundation (2026-07-09)

- **feat: monorepo scaffold (uv + pnpm workspaces, justfile, lint/test gates)**
  — `services/{gateway,documents,geometry}` + `packages/{py-kit,contracts,ts-client,design}`
  - `apps/web` + `deploy/` directories created. Python workspace (uv 0.5+,
    Python 3.12, pyproject.toml per package), TypeScript workspace (pnpm 10,
    package.json per package). Justfile with `lint` / `test` / `dev` / `gen` /
    `e2e` targets. ruff (lint + format), pyright (strict), eslint (flat),
    prettier configs. `just lint` and `just test` green.

- **feat(py-kit): service bootstrap — config, JSON logging, app factory, error
  envelope, queue client**
  — `packages/py-kit/`: pydantic-settings BaseServiceSettings (env-driven config),
  structlog JSON logging with request-context binding (console renderer via
  LOG_FORMAT=console), ApiError hierarchy + standard error envelope (404/409/422/500,
  opaque unhandled 500s), FastAPI `create_app` factory, `/healthz` + `/readyz`
  probes, thin arq QueueClient. 21 unit tests; probes verified against real
  uvicorn boot.

- **feat(services): gateway/documents/geometry skeletons on py-kit**
  — Three FastAPI services boot on py-kit with per-service Settings subclasses.
  `services/geometry` exposes `redis` + `postgres` readiness checks (report
  "skipped" while env vars unset). 19 new unit tests (40 total); all three
  probed and returned 200 health status.

### Docker & CI foundation (2026-07-09)

- **feat(platform): compose stack, parameterized service Dockerfile, smoke +
  dev-instance scripts**
  — `deploy/docker/service.Dockerfile`: ONE multi-stage Dockerfile parameterized
  via build-arg `SERVICE_NAME` (deps layer cached on uv.lock, non-root user,
  curl HEALTHCHECK on `/healthz`). `docker-compose.yml`: Postgres 16 + Redis 7
  - MinIO + three services, datastore healthchecks, service_healthy depends_on,
    env wiring, named volumes. `docker-compose.dev.yml`: hot-reload override
    (bind-mounted src via PYTHONPATH + uvicorn --reload). Helper scripts:
    `scripts/smoke-healthz.sh` (health/readiness table, retries), `scripts/dev-instance.sh <N>`
    (offsets to run parallel instances). Both configs validate; smoke passed
    6/6 against bare-uvicorn boot. **Compose runtime not verified in this sandbox
    (no docker daemon)** — tracked as new ROADMAP Phase 0 item.

- **ci: lint/typecheck/test, contract drift, compose validation workflow**
  — `.github/workflows/ci.yml`: four parallel jobs (python, ts, contracts,
  compose). Triggers: push to main + `claude/**`, PRs. Per-ref concurrency,
  ≤15 min timeouts, pinned actions. Python job: uv sync --locked, ruff + pyright,
  pytest. TS: pnpm frozen install, eslint + prettier, vitest. Contracts:
  `just gen-check` (drift gate). Compose: `docker compose config`. First
  hosted run on push. Workflow authored + every command verified locally.

### API contract pipeline (2026-07-09)

- **feat(contracts): pydantic→OpenAPI→TS client pipeline with drift check**
  — `scripts/gen-contracts.py`: imports service `build_app()`, exports
  deterministic OpenAPI JSON to `packages/contracts/<service>.openapi.json`
  (sorted keys, 2-space indent, trailing newline). `scripts/gen-ts-client.mjs`:
  generates `packages/ts-client/src/<service>/` (openapi-typescript schema.ts +
  openapi-fetch index.ts wrapper, "GENERATED" headers). `just gen` runs both
  (idempotent); `just gen-check` regenerates in tempdir and diffs (fails on
  contract OR client perturb, never dirties tree). Generated code excluded from
  linters. `@loft/ts-client` is source-only with per-service exports and strict
  `tsc --noEmit`.

### Kernel & geometry foundation (2026-07-09 to 2026-07-10)

- **feat(geometry): OCCT kernel first light — parametric box, tessellation to
  GLB, mass properties**
  — `services/geometry`: OCCT via build123d for parametric solid modeling. Box
  builder accepts x/y/z mm dimensions, evaluates B-rep, tessellates to
  byte-deterministic GLB (identical across runs). Exports `POST /api/v1/tessellate`
  - `/tessellate/meta` endpoints. Mass properties (volume, area, centroid) and
    topology counts (faces/edges/shells) computed exactly. Golden 10×20×30 box:
    6000 mm³ / 2200 mm² / centroid (5,10,15), 6/12/1 topology, <2 s perf tripwire
    (4–8 ms warm). Asserted analytically at 1e-7 kernel tolerance.

- **feat(gateway): geometry tessellation proxy + shared DTOs in py-kit**
  — Gateway now surfaces geometry service: `POST /api/v1/geometry/tessellate`
  (GLB passthrough incl. X-Loft-Properties header via lifespan-managed httpx2
  AsyncClient, 30s budget). Transport failures map to py-kit 502
  `upstream_unavailable` envelope; upstream errors re-surfaced. `POST
/api/v1/geometry/tessellate/meta` JSON twin. GatewaySettings.geometry_url
  env wire (GEOMETRY_URL; compose defaults to http://geometry:8002). Boundary
  DTOs moved to `py_kit.schemas.geometry` (single source of truth); geometry
  re-exports. Contracts + ts-client regenerated.

### Frontend & design (2026-07-10)

- **feat(web): first light — design tokens, app shell, r3f viewport rendering
  OCCT-tessellated geometry**
  — `packages/design` v1: machine-shop token system (carbide/anvil/mist/gauge +
  one brass accent + aluminum model material; all text pairs ≥7:1, control
  borders ≥3:1 verified numerically). Hanken Grotesk UI + Fragment Mono data
  faces, self-hosted via @fontsource. Tailwind preset derived FROM TS token
  constants (one palette, two renderers). First primitives: Button, Panel/Section/Row
  (signature "title block"), Toolbar, Chip, NumberField.
  — `apps/web`: Vite + React 19 + strict TS, TanStack Router (/) + Query,
  zustand viewport store. r3f viewport renders gateway-proxied OCCT GLB
  (per-face primitives merged client-side, mm-scaled, token-driven materials +
  B-rep edge overlay, GPU disposal on swap, frameloop=demand, reduced-motion
  honored). Engineering-drawing title block inspector with live mass properties
  parsed from X-Loft-Properties header. Keyboard-first x/y/z dimension form
  re-tessellating live. Typed exclusively via generated `@loft/ts-client/gateway`;
  zero hex literals.
  — Tests: 13 vitest units (header parsing, dimension validation); 4-spec
  Playwright e2e against real geometry+gateway stack (6000 mm³ assertion,
  non-empty canvas, per-keystroke edit to 3840 mm³, 1280×800 layout). Founder
  screenshots in `docs/screenshots/first-light-*.png`.
  — Honest note: async queue leg still sync-inline; arq/redis runtime lands
  with queue/storage backlog items.

### Geometry QA (2026-07-10)

- **test(geometry): golden-model harness, first golden (cube), STEP
  round-trip gate**
  — `services/geometry/tests/test_goldens.py`: data-driven pytest runner
  discovers `services/geometry/goldens/<name>/{model,expected}.json`. Asserts
  mass properties within each golden's documented tolerance + rationale,
  topology/mesh counts exactly, determinism at byte strength both in-process
  and across interpreter restart (worker-restart emulation). Adding a golden
  requires zero runner changes; inventory guard tests fail if discovery breaks.
  Subsumes old `test_kernel` determinism test.
  — First golden: `goldens/box-10x20x30/`. Expected: 6000 mm³, 2200 mm², centroid
  (5,10,15), 6/12/1 topology, 24 vertices / 12 triangles, all at 1e-7. Measured
  deviation: 0.0.
  — `services/geometry/tests/test_step_roundtrip.py`: parametrized over golden
  inventory. Build → export_step → import_step → re-measure. Measured deviation
  exactly 0.0 on all 11 mass-property checks; topology preserved. Harness
  proven to fail on perturbed volume/topology before commit.
  — `docs/GEOMETRY-QA.md`: first dated entry with evidence tables, run commands,
  determinism digests, perf numbers (3.8–4.3 ms warm), 7-item coverage-gap list.
  — Test count: just test reports 76 pytest + 13 vitest = 89 green.

### Community & documentation (2026-07-10)

- **docs: community surface — truth-only README, CONTRIBUTING, SECURITY,
  templates**
  — `README.md` rewritten: CI + MIT badges, first-light hero screenshot, four
  structural advantages, honest Phase 0 status, verified quickstart + bare-metal
  dev flow (every command re-run in sandbox incl. live 6000 mm³ tessellate
  through gateway). Compose path labeled runtime-unverified.
  — `CONTRIBUTING.md`: verified dev setup, CI gates table, conventions,
  docs-sync + conventional-commit PR expectations, agent-team note.
  — `SECURITY.md`: private GitHub advisories, main-only support, no bounty,
  honest scope notes.
  — `CODE_OF_CONDUCT.md`: Contributor Covenant 2.1.
  — `.github/ISSUE_TEMPLATE/bug_report.yml` + `feature_request.yml`: structured,
  verified against known runtime/commit/env variables.
  — `.github/ISSUE_TEMPLATE/config.yml`: security contact link.
  — `.github/PULL_REQUEST_TEMPLATE.md`: mirrors definition of done.

## [Phase 1: MVP — sketcher/export foundations, batch 1] — 2026-07-10

- **docs: feature-tree persistence design** (952e86a) — `docs/design/
feature-tree.md`: features table vs JSONB tradeoff, versioned param
  envelope, `GeomRef`, rollback bar, evaluation contract, alembic plan.
- **feat(platform): wire `just e2e`** (1baa986) — `scripts/e2e.sh` runs
  geometry gates + Playwright, self-managed service boot/reuse (GEOMETRY-QA
  gap #6).
- **docs(design): revise feature-tree design per code-reviewer** (485ac3a) —
  FK `ON DELETE` fix, reverse-lookup index, DB-enforced same-part invariants;
  verdict resolved.
- **feat(geometry): STEP/STL export endpoints** (12e7b4e) — byte-deterministic
  STEP (pinned timestamp)/STL, endpoint-level round-trip at 0.0 deviation
  (GEOMETRY-QA gaps #3/#4 closed).
- **feat(gateway): export proxy** (c5e2b1e) — `POST /api/v1/geometry/export`
  passthrough with media type + `Content-Disposition`.
- **feat(geometry): SketchSolver interface + planegcs spike** (3da8f0a) —
  verdict: planegcs adopted (LGPL-2.1 verified), benchmark rectangle 0.0
  deviation, bitwise-deterministic.
- **feat(geometry): first curved golden** (9765c2c) — `cylinder-r10-h25`,
  1e-9 measured curved-GProp tolerance, seam-edge topology, curved STEP
  round-trip baseline (GEOMETRY-QA gap #1 closed).
- **feat(web): STEP/STL download UI** (8cd63d5) — title-block EXPORT row,
  new `PanelActionCell` primitive, real-browser download e2e; closes the
  export item end to end.
- **docs(vision): re-score daily-driver scorecard** (95617d1) — Interop
  half-flipped (export shipped, import Phase 4); other rows refreshed.
- **feat(gateway): auth v1** (b82a091) — argon2id + HS256 JWT
  register/login/me, fail-fast `JWT_SECRET` posture, hard postgres
  readiness.
- **feat(documents): parts CRUD** (ba40016) — owner-scoped CRUD + alembic
  `0001_parts`, auth-protected gateway aggregation.
- **feat(web): auth v1 sign-in** (9fde895) — drawing-sheet sign-in/register,
  session persistence, global expiry notice; 15/15 Playwright green.
- **fix(gateway): fail-closed auth posture** (6479c10, 565e337) — fail-closed
  `LOFT_ENV`, argon2 off the event loop, secret `.strip()`, login password
  cap; run-command docs updated to match.
- **docs(board): groom for Phase 1** (35bd7ec) — Ready queue sequenced
  (export/cylinder/design-doc/spike/auth/CRUD/e2e), Scorecard-gaps note
  added, Phase 0 archived. [backlog-groomer]

## [Phase 1: MVP — sketcher/Features-v1, batch 2] — 2026-07-11

- **feat(documents): feature-tree persistence — schema + API slice** (6b6ff36)
  — alembic `0002_feature_tree`, feature CRUD/reorder/rollback with §2.2
  reference rules, 409-with-dependents, 422-stale-version.
- **feat(geometry): evaluate-tree slice** (23004a5) — stateless
  `POST /api/v1/evaluate`, ordered dispatch, strict-prefix partial results,
  sketch-only handler registry.
- **feat(sketch): sketch model + solver API** (8831c21) — typed sketch
  entity/constraint schemas, §6 worked example solved end-to-end at 0.0
  deviation, DOF 0, over real HTTP.
- **feat(web): sketcher v1** (91fa1d1) — `/parts/{id}` workspace: datum-plane
  pick, L/R/C/A click-to-place tools, 1 mm-snap DRO, save→evaluate→render;
  e2e 19/19.
- **docs(board): file parts-home UI item** (cadeb31) — workspace was
  direct-URL-only.
- **feat(web): sketcher constraints + solve feedback** (75f0214) — H/V/D/R/X/C
  verbs, in-viewport glyphs with inline dimension edit, live
  save→solve→adopt loop, DRO DOF cell, conflict diagnostics; e2e 25/25.
- **docs(board): file structured conflict-indices item** (17668b2) — frontend
  parses error text today, filed for a typed field.
- **feat(geometry): extrude (add/cut) end-to-end** (11eaa65) — first
  body-affecting feature; golden `sketch-extrude-40x25x10` (1e-9 tolerance,
  0.0-dev STEP round-trip), strict-prefix broken-profile case, §7.8 interim
  content-addressed mesh endpoint.
- **docs(board): groom for Phase 1 wrap-up** (35bd7ec) — ROADMAP golden
  count fixed (2→3 of 5); Ready refilled toward the exit gate: mesh-fetch
  gateway proxy + viewport render, extrude UI, parts home, fillet/chamfer
  split, export-from-tree, full-flow e2e. [backlog-groomer]

## [Phase 1: MVP complete — exit-gate batch] — 2026-07-11

- **feat(gateway): mesh-fetch proxy** (8680502) — content-addressed GLB
  proxy, byte-identical to geometry's endpoint, auth-protected.
- **feat(web): render evaluated-tree bodies** (90f813f) — the extrude loop
  becomes visible: aluminium + B-rep edges, title-block body inspector.
- **feat(web): extrude authoring UI + feature-tree edit/rollback** (e80e378)
  — title-block extrude editor, selectable tree rows, brass rollback bar.
- **feat(web): parts home** (6a9a885, 4bdc27f) — drawing-register
  create/list/open/delete; box demo moved to `/first-light`.
- **feat(geometry): fillet feature** (56eebb0) — geometric edge selection
  (`EdgeSelector`, design §2.4), golden `fillet-plate-r5` at 1e-9.
- **feat(geometry): chamfer feature** (02b6e9c) — reuses fillet's shared
  `select_edges` (DRY), golden `chamfer-plate-d5`, exact 0.0 STEP round-trip.
- **feat(geometry): export-from-tree** (aad27d9) — `POST /api/v1/export/tree`
  - gateway `POST /api/v1/parts/{id}/export`; closes GEOMETRY-QA gap #8.
- **feat(web): full-flow e2e — the Phase 1 exit gate** (ff6b226) — login →
  sketch → extrude → edit param → export proven in a real browser, desktop +
  1280×800 + touch smoke; web part-export strip shipped alongside.
- **docs(vision): re-score post-exit-gate** (8a67e93) — Part modeling and
  Interop deepen but stay ❌ (3 features/predicate edge selection; export
  covers modeled trees but import is still Phase 4); Sketching unchanged.
- **docs(board): groom for Phase 2** (this pass) — ROADMAP Phase 1 → ✅,
  Current focus → Phase 2; Ready batch 3 archived; new Phase 2 Ready queue
  (topological naming design doc, sketch constraints, revolve, measurement,
  pattern). [backlog-groomer]
