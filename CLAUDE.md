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
2. **Design system first.** Tokens + `apps/web/src/components/ui/*` are the
   single source of truth; screens compose primitives. Fix the primitive,
   never the instance (this is the DRY rule applied to design).
3. **The viewport is the hero.** Chrome recedes; the model gets the pixels.
   Panels, trees, and toolbars are quiet precision instruments — dense,
   legible, keyboard-first — not marketing surfaces.
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
deploy/             Docker/Helm assets
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, audits, QA reviews
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
- **Frontend primitives:** design tokens + `apps/web/src/components/ui/*` are
  the single source; components derive from them.
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
just test           # all unit tests (py + ts)
just lint           # ruff + pyright + eslint
just gen            # regenerate contracts + ts-client
just e2e            # Playwright + geometry golden suite
docker compose up -d --build   # full stack
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

## Environment recipes (hard-won — append as you learn)

Next-Lane's equivalent section was earned through painful debugging; ours
starts small. **When you burn >15 minutes on an environment quirk, append the
recipe here in the same commit as the fix.**

- Working branch: develop on the current `claude/*` branch; never push to
  `main` without explicit permission.
- OCP/OCCT wheels are large; in CI cache the uv environment keyed on the
  lockfile.
