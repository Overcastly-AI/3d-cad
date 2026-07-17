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
