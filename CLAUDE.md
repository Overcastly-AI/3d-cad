# CLAUDE.md — Loft (working name)

Guidance for Claude Code (and other AI agents) working in this repository.

## What this is

An **open-source, cloud-native parametric 3D CAD platform** — Python
microservices backend (OCCT geometry kernel), React frontend, MIT licensed,
self-hostable, built to compete with the industry daily drivers.

**North star: `docs/VISION.md`.** The operating question every decision
answers is **"Would a working engineer model a real part in this today?"**
The daily-driver scorecard in VISION.md keeps that answer honest and directs
prioritization. The founder dreams in plain language; the **vision-steward**
agent turns those ideas into VISION/ROADMAP/BACKLOG entries.

**Architecture decisions live in `docs/RESEARCH.md`** (kernel, solver,
service boundaries, stack). Do not change them without updating that file in
the same commit.

## Operating principles (own the outcome)

You run this team. Do not wait to be told to optimize, fix process, or raise
quality — that is your job.

1. **Be proactive.** If the workflow, an agent, or a skill is slowing us down
   or letting defects through, change it (update `.claude/` and these docs)
   without being asked.
2. **Ship quality the *user* feels.** "Tests pass" ≠ "works for the user." QA
   exercises the **real artifact**: the actual compose build, real modeling
   flows end-to-end in a real browser, and — because this is CAD —
   **geometric correctness** (golden models, STEP round-trips, solver
   determinism; see `docs/RESEARCH.md` §9). A green unit suite with a wrong
   volume is a failure.
3. **No hand-waving.** Never dismiss a failing test or wrong geometry as
   "pre-existing" or "tolerance noise" without root-causing it.
4. **Parallel by default.** Isolated git worktrees + per-instance
   compose/ports for disjoint items. Serial is the exception.
5. **Converge.** Drive the current ROADMAP phase to done, then polish. Work
   that flips a ❌ row on the VISION.md scorecard outranks new pillars.
6. **Keep docs honest** (below) and **never push a red build.**

## Design mandate — STANDING FOUNDER PRIORITY (UI/UX)

Frontend design is a first-class product goal, not polish. CAD tools are
where engineers live all day; ours must look and feel **premium, distinctive,
and intentional** — never templated. Standing rules:

1. **Always use the `frontend-design` skill** (`.claude/skills/frontend-design/`,
   vendored Anthropic skill). ANY UI work — new surface, component, or
   redesign — invokes it first: establish/extend the token system (palette /
   type / layout / **one signature element**), avoid the AI-default looks it
   names, spend boldness in one place, keep the rest disciplined.
2. **Design system first.** `packages/design` (tokens + primitives + fonts)
   is the single source of truth; screens compose primitives. Fix the
   primitive, never the instance (this is the DRY rule applied to design).
   Both renderers draw from it: Tailwind preset for the DOM, TS token
   constants for the WebGL viewport — one palette, two renderers.
3. **The viewport is the hero.** Chrome recedes; the model gets the pixels.
   Panels, trees, and toolbars are quiet precision instruments — dense,
   legible, keyboard-first — not marketing surfaces.
3a. **Tool-grade viewport, benchmarked against Fusion 360 / Plasticity**
   (founder recalibration 2026-07-16 — "premium dashboard" is NOT the bar;
   *feels like a modeling tool* is). Concretely: (a) the 3D scene fills the
   frame with depth — grid reads to the horizon (no mid-frame fade into flat
   void), background has atmosphere (gradient/fog/vignette), bodies get
   studio-quality shading (matcap/env — Plasticity's look), never debug-gray;
   (b) persistent view navigation: a ViewCube/gizmo + home/iso/ortho snaps
   is table stakes, not a feature; (c) **every chrome element is functional**
   — a tile/readout that only decorates is a defect; wire it or delete it;
   (d) judge screenshots side-by-side against a Fusion/Plasticity reference
   before calling UI work done.
4. **Show, don't tell.** UI changes ship with before/after screenshots
   (desktop + small-laptop widths) surfaced to the founder at milestones.
5. **Never break the product for looks.** Preserve test hooks (`data-testid`,
   roles, accessible names). Quality floor: WCAG-AA contrast, visible focus,
   `prefers-reduced-motion`, self-hosted fonts, responsive to 1280×800.

## Stack (change only with docs/RESEARCH.md + docs/ARCHITECTURE.md updates)

- **Backend:** Python 3.12+, FastAPI microservices; OCCT via OCP + build123d
  (geometry service ONLY); Postgres 16; Redis 7 + arq; MinIO/S3.
- **Frontend:** React 19 + Vite + TypeScript; TanStack Router + Query;
  Tailwind + shadcn/ui; react-three-fiber + drei; zustand.
- **Monorepo:** uv workspaces (Python) + pnpm workspaces (TS) + `justfile`.
- **Infra:** Docker Compose for dev/small self-host; Kubernetes (Helm) later.

## Layout

```
apps/web            React SPA (viewport + UI)
services/gateway    FastAPI: auth, REST aggregation, WebSocket fan-out
services/geometry   OCCT workers: feature eval, tessellation, export (stateless)
services/documents  Parts/assemblies, feature trees, versioning (Postgres)
packages/py-kit     Shared Python service kit (config, logging, health, queue, errors)
packages/contracts  Generated OpenAPI schemas (committed; CI checks drift)
packages/ts-client  Generated TypeScript client (never hand-edited)
packages/design     Design system: tokens (Tailwind preset + TS constants),
                    UI primitives, fonts (source-only; RESEARCH §5)
deploy/             Docker/Helm assets
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, COMPETITIVE, audits, QA reviews
.claude/            Agents, skills, workflows
```

## DRY — NON-NEGOTIABLE

WET code is a defect class here, reviewed as such:

- **One source of truth for types:** pydantic models → generated OpenAPI
  (`packages/contracts`) → generated TS client (`packages/ts-client`).
  Hand-written duplicates of API types, in Python or TS, are rejected in
  review. Regenerate with `just gen`; CI fails on drift.
- **Cross-service boilerplate lives in `py-kit` once** — config, logging,
  health/readiness, error envelope, queue plumbing. If you're copying code
  between services, stop and move it to `py-kit`.
- **Frontend primitives:** `packages/design` (tokens + UI primitives + fonts)
  is the single source; `apps/web` composes it and never restyles raw
  elements. The r3f viewport reads the SAME tokens (selection/hover/grid/
  background) — no hex values duplicated between DOM and WebGL.
- DRY ≠ premature abstraction: extract on the second real use, not the first
  imagined one.

## Service boundaries (enforced in review)

- Only `services/geometry` imports OCP/build123d. No kernel types cross a
  service boundary — meshes/exports go to object storage, references by ID.
- `services/geometry` never touches Postgres; `services/documents` never
  imports the kernel; `apps/web` talks only to the gateway.
- **No GPL/AGPL dependencies** (MIT app; LGPL-dynamic ok — RESEARCH §8).

## Commands

```bash
just dev            # compose up db/redis/minio + services + web (hot reload)
just dev-down       # tear down the dev stack (keeps volumes)
just smoke          # probe /healthz + /readyz on all services
just lint           # ruff + pyright + eslint/prettier + TS typecheck (tsc)
just test           # all unit tests (py + ts)
just gen            # regenerate contracts + ts-client
just gen-check      # CI gate: regenerate in tempdir, diff vs. committed
just e2e            # geometry gates (goldens + STEP round-trip) + Playwright suite;
                    # boots geometry/gateway itself (PID-tracked, cleaned up)
docker compose up -d --build   # full stack (use `just dev` for dev with hot reload)
```

(Targets land with the monorepo scaffold; keep this section true as they do.)

## Conventions

- Strict typing both sides: pyright-clean Python (no untyped defs in
  services/packages), strict TypeScript (no `any` without justification).
- DB changes via migrations only (alembic), never ad-hoc SQL.
- Geometry tolerances: linear 1e-7 m kernel-side; golden-suite assertions use
  documented per-model tolerances, never ad-hoc epsilons.
- API: REST, versioned under `/api/v1`; error envelope from `py-kit`.
- Conventional-commit messages; one logical item per commit.

## Keep the docs in sync — NON-NEGOTIABLE

Stale docs are a defect (this rule saved Next-Lane repeatedly; see
`docs/AUTONOMOUS-LOOP.md`).

- **Every commit that lands a feature/fix MUST, in the same commit, update
  `docs/ROADMAP.md` and `docs/BACKLOG.md`.** A commit that ships work but
  leaves the roadmap stale is incomplete.
- `docs/ROADMAP.md` is the source of truth for "what phase are we in"; its
  status markers and "Current focus" line must always match `git log`.
- Every groom pass reconciles ROADMAP + BACKLOG against git history.
- **Definition of done for ANY change** = builds + lint/typecheck + unit
  tests green + geometry gates green (when kernel-adjacent) + e2e green (when
  user-facing) + ROADMAP/BACKLOG ticked + committed & pushed. For new
  capabilities: scripting/MCP exposure where sensible (or an explicit "not
  agent-appropriate" note) once Phase 5 lands the surface.

## Work as a dev team

Built by a **team of specialized AI agents**, not one generalist. Default to
delegating. The tooling lives in [`.claude/`](./.claude/README.md).

**Builders:** `kernel-architect` (geometry service, kernel layer, solver),
`backend-builder` (gateway/documents, py-kit), `frontend-builder` (web app,
viewport), `platform-builder` (Docker/compose/CI/Helm, contract pipeline).

**Quality (independent of whoever wrote the code):** `code-reviewer`,
`qa-tester` (Playwright, real stack, desktop + touch), `geometry-qa` (golden
models, round-trips, benchmarks → `docs/GEOMETRY-QA.md`), `frontend-qa`
(design/a11y/consistency → `docs/UI-REVIEW.md`).

**Direction (read-only on app code):** `product-auditor` +
`engineering-auditor` (independent, don't coordinate), `backlog-groomer`,
`vision-steward`, `doc-syncer` (cheap-model doc reconciler, every iteration),
`oss-curator` (README/community surface, truth-only).

**The loop for every feature:** plan → implement (specialist) → review
(`code-reviewer`) → QA (`qa-tester`; `geometry-qa` when kernel-adjacent;
`frontend-qa` spot-check) → tick ROADMAP/BACKLOG → commit. Workflows in
`.claude/workflows/` orchestrate this; `autonomous-dev-loop` chains batches
on completion with a watchdog fallback (`docs/AUTONOMOUS-LOOP.md` §1.4).

## Multi-agent orchestration protocol

- **File territories.** Parallel agents get explicitly disjoint territories in
  their briefs (e.g. one holds `services/geometry/**`, another `apps/web/**`).
  Never edit, revert, or commit another agent's in-flight files. Foreign
  uncommitted work in shared files: build alongside, stage only your hunks.
- **Commit protocol:** stage your own files explicitly — never `git add -A`.
  Push with `git push -u origin <branch>`; on rejection `git pull --rebase`
  and retry. Commit only when your gates are green.
- **Liveness (orchestrator duty).** On every wakeup, check in-flight agents'
  output mtimes; >30 min stale without a known long gate = investigate, reap,
  relaunch. A dead agent's uncommitted work is preserved and reconciled by
  its relauncher, never reverted.
- **Verify before trusting.** The orchestrator re-runs a targeted slice of a
  completed agent's gates before reporting its work done.
- **Run gates in the foreground** — never end a turn waiting on your own
  backgrounded build/test.
- **Founder updates are results-first:** what shipped + evidence
  (numbers, screenshots), then what's running, then what's next — proactively
  at milestones.

## Token economy (founder priority 2026-07-10 — quality-neutral savings only)

Usage-limit interruptions cost more than they save; spend tokens where
quality lives (builders, reviewers, geometry QA) and trim everywhere else:

- **Model tiers:** direction/docs roles (groomer, vision-steward,
  oss-curator: `model: sonnet`; doc-syncer: `haiku`) — builders, reviewers,
  and QA stay on the strong default. Never downgrade a role whose output
  gates correctness or security.
- **Lean briefs:** orchestrator briefs point at the BACKLOG item's acceptance
  criteria instead of restating them; only deltas, environment facts, and
  territory go in the brief.
- **Scoped reading:** agents read the doc *sections* they need (e.g.
  RESEARCH §N named in the brief), not every direction doc end-to-end.
- **Targeted verification:** the orchestrator re-runs a *targeted slice* of a
  completed agent's gates (the protocol's wording — not the full suite);
  the full sweep (`just lint && just test && just e2e`) runs once per batch
  end, not per item.
- **Lean shared docs:** files every agent reads must stay small. BACKLOG
  changelog entries ≤3 lines; groomer prunes older entries into CHANGELOG.md
  each pass; Done archives get collapsed to one line per item after a phase
  closes.
- **Right-size reports:** agent return reports carry evidence tails and
  decisions, not narration. Screenshots > prose for UI evidence.

## Environment recipes (hard-won — append as you learn)

Next-Lane's equivalent section was earned through painful debugging; ours
starts small. **When you burn >15 minutes on an environment quirk, append the
recipe here in the same commit as the fix.**

- Working branch: develop on the current `claude/*` branch; never push to
  `main` without explicit permission.
- OCP/OCCT wheels are large; in CI cache the uv environment keyed on the
  lockfile.
- In this container, `uv python install 3.12` fails (403: the egress proxy
  blocks github.com release downloads of python-build-standalone — a policy
  denial, don't retry/route around). Not needed: system interpreters exist at
  `/usr/bin/python3.10`–`3.13`; with `.python-version` = 3.12, `uv sync`
  picks up `/usr/bin/python3.12` automatically. PyPI + npm registries are
  direct (proxy no-proxy list), so `uv sync` / `pnpm install` just work.
- `just` is not preinstalled: `uv tool install rust-just` → `~/.local/bin/just`.
- **The Docker *registry* is blocked here, but the stack does NOT need Docker —
  a native, container-free boot works and CAN drive `just e2e` + founder
  screenshots.** `docker pull` of `postgres:16` / `redis:7` / `minio/minio:*`
  fails mid-blob with **403 Forbidden** from
  `production.cloudfront.docker.com/...blobs...` (same policy-denial class as
  the github python-build block above; don't retry/route around), so the
  *compose* stack can't build. But every external is OPTIONAL and the services
  run natively via uvicorn, so the whole app boots with no containers:
  - **documents / gateway → SQLite.** Each needs a schema. Do NOT run alembic
    against SQLite: the migrations render Postgres DDL verbatim (e.g.
    `created_at DATETIME DEFAULT (now())`) and SQLite has no `now()` →
    `OperationalError` at insert time. Instead create the schema with
    SQLAlchemy `metadata.create_all` (renders dialect-correct DDL —
    `CURRENT_TIMESTAMP` on SQLite), exactly as `scripts/e2e.sh` and the unit
    suites do:
    ```python
    from sqlalchemy.ext.asyncio import create_async_engine
    from documents.db import Base as D; from gateway.db import Base as G
    from py_kit.db import async_dsn
    for url, base in ((doc_dsn, D), (gw_dsn, G)):
        e = create_async_engine(async_dsn(url))
        async with e.begin() as c: await c.run_sync(base.metadata.create_all)
        await e.dispose()
    ```
    DSNs are file URLs: `sqlite+aiosqlite:////abs/path/documents.db` (the env
    var is `POSTGRES_URL`; `py_kit.db.async_dsn` normalizes `sqlite://` →
    `sqlite+aiosqlite://`).
  - **geometry → in-process LRU mesh store** when `S3_URL` is unset. Keep
    `--workers 1` (the LRU is per-process; multi-worker would split it). No MinIO.
  - **gateway → fail-open rate limiter** when `REDIS_URL` is unset (no-op
    dependency). WS fan-out + mate authoring are plain REST/in-proc — no Redis. 
  Boot (ports gateway :8000, documents :8001, geometry :8002 — the smoke/e2e
  defaults), after the create_all above:
  ```bash
  uv run uvicorn geometry.main:app  --host 127.0.0.1 --port 8002 --workers 1 &
  POSTGRES_URL="$DOC_DSN" uv run uvicorn documents.main:app --host 127.0.0.1 --port 8001 &
  LOFT_ENV=dev POSTGRES_URL="$GW_DSN" GEOMETRY_URL=http://127.0.0.1:8002 \
    DOCUMENTS_URL=http://127.0.0.1:8001 \
    uv run uvicorn gateway.main:app --host 127.0.0.1 --port 8000 &
  scripts/smoke-healthz.sh 8000   # all three /healthz+/readyz → 200
  ```
  `LOFT_ENV=dev` is required (the gateway fail-closes on JWT posture otherwise).
  Then Vite: Playwright's `webServer` boots it itself (`reuseExistingServer`),
  so just run the specs — the Vite `/api` proxy defaults to `:8000`; set
  `GATEWAY_ORIGIN=http://127.0.0.1:8000` explicitly to be safe. Founder
  screenshots: `UPDATE_SCREENSHOTS=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
  pnpm --filter @loft/web exec playwright test e2e/<spec>.ts`. This is how the
  UR3 / units / mate / drawings founder shots under `docs/screenshots/` were
  captured natively (2026-07-18) — **e2e + screenshots are NOT CI-only.**
  Runnable gates here therefore include the full Playwright e2e, not just
  `pnpm --filter @loft/web {typecheck,test}` + `just lint` + geometry `pytest`.
  (Only `just dev` / `docker compose` proper — which build the container images —
  still can't run; use the native boot above instead of the compose stack.)
- **Stale dev uvicorns poison `just e2e`.** Long-lived service uvicorns (from a
  prior `just dev` or an agent that booted the stack) run **without**
  `--reload`, so after any backend commit their served OpenAPI/routes go stale.
  `just e2e` (and `just smoke`) **reuse healthy listeners** on :8000/:8001/:8002
  rather than rebooting, so a batch-end e2e will 404 on newly-added routes and
  fail specs that are actually green against HEAD. Before a batch-end `just
  e2e`, kill lingering `*.main:app` uvicorns:
  `ps -eo pid,args | grep -E '(gateway|geometry|documents)\.main:app' | grep -v grep`
  then `kill` those pids (parents + children) so the suite reboots from current
  code. Agents that need a stack mid-run should boot **isolated** ports (e.g.
  :8010/:8012) and tear them down, leaving the shared stack untouched.
- **A stale Vite on :5173 poisons `just e2e` worse than a stale uvicorn — every
  spec 500s at register.** `apps/web/playwright.config.ts` sets
  `reuseExistingServer: true` (so e2e composes with a running `just dev`), and
  the Vite `/api` proxy targets `GATEWAY_ORIGIN ?? http://127.0.0.1:8000`
  (`apps/web/vite.config.ts`). An agent that booted an **isolated** frontend
  (its own Vite on :5173 with `GATEWAY_ORIGIN=http://127.0.0.1:8010`) and tore
  down its :8010 gateway but **left the Vite process running** leaves a
  :5173 whose proxy now points at a DEAD gateway. A later shared `just e2e`
  *reuses that stale Vite* → `/api/v1/auth/register` proxies to nothing →
  **500**, and since every spec's `seedSession` registers first, the WHOLE
  suite fails ("e2e register failed: 500", ~157 failed / 2 passed) while
  leg-1 geometry gates pass and a direct curl to the real :8000 gateway
  returns 201. Symptom ≠ code regression. **Before a batch-end `just e2e`,
  also kill a stale Vite:** `curl -sf -m2 http://127.0.0.1:5173/ >/dev/null &&
  ps -eo pid,args | grep -E 'vite/bin/vite' | grep -v grep` then `kill` it, so
  Playwright boots a fresh Vite proxying to the :8000 gateway `just e2e`
  starts. Agents booting an isolated frontend MUST kill their Vite in teardown,
  not just their uvicorns.
- **After a CONTAINER RESTART, real-pointer pick specs + pixel-fit asserts can
  go red ENVIRONMENTALLY — bisect against a pre-restart-green commit before
  blaming code.** Seen 2026-07-22: the batch-end `just e2e` failed 6 specs (5
  measure vertex/corner picks — readout never appears — + undo-redo's 1280
  command-band ≤0px fit, "Received: 1"). Four-point bisect (HEAD → `0c10265` →
  `47c88f4` → `24b1c53`) reproduced the SAME failures at a commit that was
  full-suite green in the pre-restart container: the restart's Chromium/GL
  raster + font metrics shifted sub-pixel, real-pointer pick coordinates
  computed from live canvas geometry now miss, and a 1px band measurement
  drifted. Verdict procedure: rerun the failures in ISOLATION first (flake
  check), then bisect to a known-green-in-a-previous-container commit — same
  failures there = environment. Fix is spec robustness (tracked in BACKLOG:
  raster-tolerant picks + toleranced px asserts), not code reverts.
- **Founder screenshots are refresh-on-demand, not a per-run output.** `just
  e2e` used to rewrite ~90 PNGs under `docs/screenshots/` every run, forcing a
  noise commit. Two churn sources: (1) the per-run random session email in the
  header (`uniqueEmail()`), and (2) Chromium's screenshot pixels are **not**
  byte-identical across a full run even with software GL — sub-pixel raster/
  camera state flips a few AA pixels (thousands over a dense sketch grid) purely
  from browser-process state; it's byte-stable in isolation but not under load,
  so pure determinism can't win. Fix (all in `apps/web`, one seam in
  `e2e/fixtures.ts`): the shared `test` fixture wraps `page.screenshot` to
  normalise the header email, freeze animations/caret, wait for `document.fonts.
  ready`, and **skip the file write for `docs/screenshots/**` unless
  `UPDATE_SCREENSHOTS=1`**. Routine e2e captures (still exercising the render)
  but never overwrites the committed PNGs → tree stays clean. To refresh the
  founder shots deliberately: `UPDATE_SCREENSHOTS=1 pnpm --filter @loft/web e2e`
  (config forces portable software-GL rendering so any contributor regenerates
  near-identical baselines). Specs import `test`/`expect` from `./fixtures`, not
  `@playwright/test`. NB: `reducedMotion` is NOT a top-level Playwright `use`
  option in 1.56 (`use.contextOptions.reducedMotion`), and enabling it snaps the
  r3f camera, which shifts face-pick screen coords and flakes the pick specs —
  left off deliberately.
- **`ruff check` + `pyright` is NOT the lint gate — `just lint` is.** CI
  (`.github/workflows/ci.yml`) runs `uv run ruff format --check .` AND
  `prettier --check .` (via `just lint`), and `ruff` is lock-pinned (uv.lock →
  0.15.20; `pyproject` floor `>=0.12` is a red herring — `uv run ruff` uses the
  locked version, the same one CI's `uv sync --locked` installs, so a local
  `ruff format --check` failure is NEVER "version skew," it's a real red build).
  A per-slice gate of only `ruff check`/`pyright`/`gen-check`/`web typecheck`
  passes while `ruff format`- and prettier-dirty files accumulate — then the
  batch-boundary `just lint` goes red (seen 2026-07-19: 4 `ruff format`-dirty
  py files + **12 prettier-dirty `goldens-sheet-metal/*.json`** slipped through
  ~10 green-looking slice commits). **Two rules: (1) every slice agent runs the
  full `just lint` before committing, not just `ruff check`; (2) newly-committed
  golden JSON (and any JSON/MD/YAML) must pass `prettier --check` — the test
  harness parses goldens as JSON (whitespace-insensitive) so a stored content
  hash is a string field unaffected by formatting, i.e. `prettier --write` on a
  golden is behaviour-neutral and safe.** Always run the full `just lint` at the
  batch boundary regardless.
