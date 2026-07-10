# Dev Board (Backlog)

Single prioritized board maintained by the **backlog-groomer**, fed by the two
independent auditors (`docs/AUDIT-PRODUCT.md`, `docs/AUDIT-ENGINEERING.md`),
QA reviews (`docs/UI-REVIEW.md`, `docs/GEOMETRY-QA.md`), and the roadmap. The
autonomous build loop pulls from **Ready (top of queue)** only.

Format: `- [ ] (P1, M) title — description [src]` · P0 critical / P1 now /
P2 next / P3 later · size S/M/L. Checked `[x]` = done.

## Ready (top of queue)

- [x] (P1, M) Monorepo scaffold — uv + pnpm workspaces (incl. empty
      `packages/design` member), justfile, ruff/pyright/eslint/prettier
      configs, root README pointers. No app code yet; `just lint` and `just
      test` pass trivially. [src: roadmap] (README pointers deferred to the
      P2 community-surface item to avoid a territory clash)
- [x] (P1, M) `packages/py-kit` — service bootstrap: pydantic-settings config,
      structlog JSON logging, FastAPI app factory with `/healthz` + `/readyz`,
      standard error envelope, arq queue client. Unit tested. [src: roadmap]
- [x] (P1, L) Service skeletons + compose — gateway/geometry/documents boot on
      py-kit, Dockerfiles, `docker compose up` brings up db/redis/minio/
      services; smoke script curls all healthz. [src: roadmap] (compose
      runtime verified via config validation + bare-uvicorn smoke only — this
      sandbox has no docker daemon; runtime `up` check is a new ROADMAP item)
- [x] (P1, M) Contract pipeline — `just gen` exports OpenAPI from services to
      `packages/contracts`, generates `packages/ts-client`; CI fails on drift.
      [src: roadmap] (drift check ships as `just gen-check`; wiring it into CI
      is the CI-pipeline item below)
- [x] (P1, L) Web shell + first light — Vite React app, TanStack Router
      layout, r3f viewport; geometry service tessellates a parametric cube to
      GLB via the queue; viewport renders it. Proves HTTP → queue → OCCT →
      GLB → viewport. **Includes the initial design token system in
      `packages/design`** (palette / type / layout / signature element —
      Tailwind preset + TS constants + fonts) via the mandatory
      `frontend-design` skill; the r3f scene reads the same tokens. The
      shell must land distinctive, not templated (CLAUDE.md design mandate).
      [src: roadmap, founder] (queue leg still sync-inline — geometry
      evaluates in-request; arq/redis runtime lands with the queue/storage
      items. E2E runs via `pnpm --filter @loft/web e2e` until the justfile
      `e2e` target is wired — platform territory)
- [x] (P1, M) CI pipeline — lint/typecheck/unit per package (path-filtered),
      compose config validation, contract drift check. [src: roadmap]
      (workflow authored + every job's command list verified passing locally;
      first hosted Actions run occurs on push. Per-package path filtering
      deferred — repo is small and all jobs run in parallel; revisit when
      job times warrant)
- [ ] (P2, M) Geometry golden harness — golden-model runner (mass properties
      + topology counts vs. committed goldens), STEP round-trip test; cube as
      first golden. [src: roadmap]
- [x] (P2, S) Community surface — README (truth-only: what runs today, no
      aspirational badges), CONTRIBUTING, SECURITY, issue templates.
      [src: roadmap]
- [ ] (P2, S) Watchdog — arm the stall-recovery routine per
      `docs/AUTONOMOUS-LOOP.md` §1.4 once the loop starts running.
      [src: retro]

## Next (P2)

- [ ] (P2, M) Auth v1 — email/password + JWT in gateway; user table in
      documents service or dedicated store per RESEARCH §3. [src: roadmap]
- [ ] (P2, L) Feature-tree persistence design doc — document model for
      parametric history (JSONB params, ordered tree, references); reviewed
      before implementation. [src: roadmap]
- [ ] (P2, M) SketchSolver interface + planegcs spike — validate the LGPL
      planegcs packaging; fall back to scipy least-squares if unworkable
      (RESEARCH §2). [src: research]

## Later (P3)

- [ ] (P3, L) Sketcher v1 UI (after solver spike + feature-tree design)
- [ ] (P3, L) Extrude/fillet/chamfer features end-to-end
- [ ] (P3, M) STEP/STL export endpoints + UI
- [ ] (P3, S) py-kit: align FastAPI 422 OpenAPI schema with the py-kit error
      envelope (currently documents HTTPValidationError)
      [src: kernel-architect]

## Changelog

- 2026-07-10 — Community surface shipped: truth-only README rewrite (CI +
  MIT badges, first-light hero screenshot, four structural advantages, honest
  "what runs / what doesn't" status with the all-❌ scorecard linked,
  quickstart + bare-metal dev flow — every command re-run and verified in
  this sandbox incl. a live 6,000 mm³ tessellate through the gateway; compose
  path presented with its runtime-unverified caveat), CONTRIBUTING.md
  (verified setup, gates table, conventions, docs-sync + conventional-commit
  PR expectations, agent-team note), SECURITY.md (GitHub private advisories,
  main-only support, no bounty, honest scope notes), CODE_OF_CONDUCT.md
  (Contributor Covenant 2.1), issue templates (bug: run-mode/commit/env;
  feature: "which structural advantage?" dropdown; config with security
  contact link), PR template mirroring the definition of done. [oss-curator]
- 2026-07-10 — Web shell + first light shipped (closes the 5c item):
  `packages/design` v1 — machine-shop token system per the mandatory
  `frontend-design` skill (carbide/anvil/mist/gauge + one brass accent +
  aluminum model material; Hanken Grotesk UI + Fragment Mono data faces,
  self-hosted via @fontsource; all text pairs ≥7:1, control borders ≥3:1
  verified numerically), Tailwind preset derived FROM the TS constants,
  first primitives (Button, Panel/Section/Row = the signature "title block",
  Toolbar, Chip, NumberField). `apps/web` — Vite + React 19 + strict TS,
  TanStack Router (`/`) + Query, zustand store, r3f viewport rendering the
  gateway-proxied OCCT GLB (one primitive per B-rep face merged client-side,
  mm-scaled, token-driven material + edge overlay, GPU disposal on swap,
  frameloop="demand", reduced-motion honored), engineering-drawing title
  block showing live mass properties from `X-Loft-Properties`, keyboard-first
  x/y/z dimension form re-tessellating live. Typed exclusively via generated
  `@loft/ts-client/gateway`; zero hex literals in apps/web (grep-verified).
  13 vitest unit tests (header parsing, dimension validation); 4-spec
  Playwright e2e against the real geometry+gateway stack asserting 6,000 mm³
  for the 10×20×30 box, a non-empty WebGL canvas, per-keystroke parametric
  edit to 3,840 mm³, and 1280×800 layout; founder screenshots committed to
  `docs/screenshots/first-light-{desktop,laptop,edited}.png`.
  [frontend-builder]
- 2026-07-10 — Gateway geometry proxy shipped: `POST /api/v1/geometry/
  tessellate` (GLB passthrough incl. X-Loft-Properties header, lifespan-
  managed httpx2 client, 30s budget, transport failures → py-kit 502
  upstream_unavailable envelope) + `/tessellate/meta` JSON twin;
  GEOMETRY_URL setting + report-only geometry readiness; boundary DTOs moved
  to `py_kit.schemas.geometry` (single source, geometry re-exports);
  contracts + ts-client regenerated. [backend-builder]
- 2026-07-10 — Geometry kernel first light shipped: OCCT via build123d in
  `services/geometry` — parametric box builder, tessellation to
  deterministic GLB (byte-identical across runs), exact mass properties +
  topology counts, `POST /api/v1/tessellate` (+ `/meta`); golden 10×20×30
  box asserted analytically at 1e-7 with 6/12/1 topology and a <2 s perf
  tripwire (4–8 ms warm). Queue verification deferred until redis runs in
  the dev stack. [kernel-architect]
- 2026-07-09 — CI pipeline shipped: `.github/workflows/ci.yml` — four parallel
  jobs. **python** (uv sync --locked, ruff check + format check, pyright,
  pytest; uv cache keyed on uv.lock so the future ~700MB OCP wheels aren't
  re-downloaded per run — CLAUDE.md recipe), **ts** (pnpm frozen install with
  store cache, eslint + prettier, recursive typecheck + test), **contracts**
  (`just gen-check` drift gate, just installed via `uv tool install
  rust-just`), **compose** (`docker compose config -q`, base and base+dev
  overlay). Triggers: push to main + `claude/**`, plus PRs; per-ref
  concurrency group cancels superseded runs; timeout-minutes on every job
  (≤15); actions pinned to major tags. Workflow authored + every job's
  command list verified passing locally; first hosted Actions run occurs on
  push. Geometry golden suite + e2e get their own workflow later (separate
  backlog items); per-package path filtering deferred until job times
  warrant. [platform-builder]
- 2026-07-09 — Contract pipeline shipped: `scripts/gen-contracts.py` imports
  each service's `build_app()` and dumps deterministic OpenAPI JSON (sorted
  keys, 2-space indent, trailing newline) to `packages/contracts/
  <service>.openapi.json`; `scripts/gen-ts-client.mjs` generates
  `packages/ts-client/src/<service>/` (openapi-typescript `schema.ts` + thin
  openapi-fetch `index.ts` wrapper, "GENERATED — do not edit" headers);
  `@loft/ts-client` is source-only with per-service exports
  (`@loft/ts-client/gateway` etc.) and a strict `tsc --noEmit` typecheck so
  generated output is provably valid strict TS. `just gen` runs both steps
  (idempotent — verified by hashing); `just gen-check` regenerates into a
  tempdir and diffs vs. committed output (fails on a perturbed contract AND
  a perturbed client file — both demonstrated; never dirties the tree; this
  is what CI will call). Generated dirs stay excluded from ruff/pyright/
  eslint/prettier; `scripts/` added to pyright strict. `just lint` + `just
  test` + `pnpm -r typecheck` green. CI wiring itself = CI-pipeline item.
  [platform-builder]
- 2026-07-09 — Compose + Dockerfiles (3b) shipped: ONE parameterized
  multi-stage `deploy/docker/service.Dockerfile` (build-arg `SERVICE_NAME`,
  uv `--frozen --no-dev --no-editable` install, deps layer cached on uv.lock,
  non-root user, curl HEALTHCHECK on `/healthz`, commented growth point for
  OCP's GL system libs); `docker-compose.yml` (postgres:16 + redis:7 + pinned
  minio + mc bucket-init + three services, datastore healthchecks,
  `service_healthy` depends_on, POSTGRES_URL/REDIS_URL/S3_URL wiring, named
  volumes, `.env.example`); `docker-compose.dev.yml` hot-reload override
  (bind-mounted src via PYTHONPATH + uvicorn --reload); `scripts/
  smoke-healthz.sh` (healthz+readyz table, BASE_PORT arg, retries, non-zero
  on failure); `scripts/dev-instance.sh <N>` (project `loft-<N>`, ports
  +N*100); `just dev`/`dev-down`/`smoke`. Verified: both compose configs
  validate, dev-instance offsets render correctly, smoke passed 6/6 against a
  bare-uvicorn boot of all three services (and fails non-zero against dead
  ports); `just lint` + `just test` green. **Compose runtime not verified in
  this sandbox (no docker daemon) — needs a Docker host** (tracked as a new
  ROADMAP Phase 0 bullet). [platform-builder]
- 2026-07-09 — Service skeletons (3a) shipped: `gateway` (:8000), `documents`
  (:8001), `geometry` (:8002) boot on py-kit `create_app` with per-service
  Settings subclasses; documents/geometry expose `postgres`/`redis` readiness
  checks that report "skipped" while POSTGRES_URL/REDIS_URL are unset (real
  pings slot in later, no probe-API change — py-kit readiness checks may now
  return a status string); geometry worker is a docstring stub, no kernel
  imports. 19 new unit tests (40 total); `just lint` + `just test` green;
  all three booted under uvicorn and probes curled 200. Compose/Dockerfiles
  (3b) pending [backend-builder]
- 2026-07-09 — `packages/py-kit` service bootstrap shipped: env-driven
  `BaseServiceSettings` (pydantic-settings), structlog JSON logging (console
  renderer via `LOG_FORMAT=console`) with request-context binding, `ApiError`
  hierarchy + standard error envelope (404/409/422/500, opaque unhandled
  500s), `create_app` factory wiring request-id middleware + `/healthz` +
  `/readyz` (per-check detail, 503 on failure), thin arq `QueueClient`.
  21 unit tests; `just lint` + `just test` green; probes verified against a
  real uvicorn boot. [backend-builder]
- 2026-07-09 — Monorepo scaffold shipped: uv workspace (`services/*` +
  `packages/py-kit`, Python 3.12) + pnpm workspace (`apps/*` + `packages/*`,
  `@loft/design` placeholder), justfile with lint/test/dev/gen/e2e targets,
  ruff + pyright(strict) + eslint(flat) + prettier configs. `just lint` and
  `just test` green. [platform-builder]
- 2026-07-09 — Founder decision: design system lives in `packages/design`
  (source-only workspace pkg: tokens as Tailwind preset + TS constants,
  primitives, fonts; one palette for DOM and WebGL). RESEARCH §5, CLAUDE.md,
  frontend agents, and the scaffold/web-shell items updated. [orchestrator]
- 2026-07-09 — Design mandate recorded (founder): frontend-design skill
  vendored and made mandatory for all UI work; web-shell item below now
  includes establishing the initial design token system. [orchestrator]
- 2026-07-09 — Board created (Phase 0 sliced from ROADMAP). [orchestrator]
