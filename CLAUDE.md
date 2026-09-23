# CLAUDE.md — Loft (working name)

Guidance for Claude Code (and other AI agents) working in this repository.

**This file holds only the CURRENT rules, each stated once.** The history
behind them (incidents, measurements, superseded versions) is in
[`docs/LESSONS.md`](docs/LESSONS.md), which is not auto-loaded. A rule's
`(why: #anchor)` names its entry there. You need that entry only for the
reason, not to follow the rule. **When a rule changes, replace it here and
move the old version to LESSONS.md. Never layer a correction on top.**
(why: #pruning-2026-09-23)

## Start here

- **Orchestrator:** open [`.claude/ORCHESTRATOR.md`](./.claude/ORCHESTRATOR.md)
  now and follow it. This file is the reference manual; that one is the
  procedure.
- **Every other agent:** read [`.claude/PROTOCOL.md`](./.claude/PROTOCOL.md)
  before your first tool call. Start, territory, commit, push, gates, stack,
  evidence and report rules live there and are not repeated here.

The four orchestrator rules, so they are in context even if you read nothing
else (why: #orchestrator-first):

1. **You dispatch and integrate. You do not do the org's job.** The
   `backlog-groomer` owns `docs/BACKLOG.md`. The auditors own the audit docs.
   Builders write code; reviewers review; QA exercises the real app. **If you
   are editing the backlog yourself, you have already gone wrong.**
2. **Use the agents.** There are fourteen in `.claude/agents/`.
3. **Builders get their own worktree** (`isolation: 'worktree'`).
4. **Reading CI is yours alone.** `api.github.com` is denied to every
   subagent. Agents push and stop; you read the run and relay failures back.

## What this is

An **open-source, cloud-native parametric 3D CAD platform**: a Python
microservices backend (OCCT geometry kernel) and a React frontend, MIT
licensed, self-hostable, built to compete with the industry daily drivers.

**North star: `docs/VISION.md`.** Every decision answers **"Would a working
engineer model a real part in this today?"** The daily-driver scorecard in
VISION.md keeps that answer honest and directs prioritization. The founder
dreams in plain language; the **vision-steward** agent turns those ideas into
VISION/ROADMAP/BACKLOG entries.

**Architecture decisions live in `docs/RESEARCH.md`** (kernel, solver, service
boundaries, stack). Do not change them without updating that file in the same
commit.

## Operating principles (own the outcome)

You run this team. Do not wait to be told to optimize, fix process, or raise
quality. That is your job.

1. **Be proactive.** If the workflow, an agent, or a skill is slowing us down
   or letting defects through, change it (update `.claude/` and these docs)
   without being asked.
2. **Ship quality the *user* feels.** "Tests pass" ≠ "works for the user." QA
   exercises the **real artifact**: the actual compose build, real modeling
   flows end-to-end in a real browser, and, because this is CAD, **geometric
   correctness** (golden models, STEP round-trips, solver determinism; see
   `docs/RESEARCH.md` §9). A green unit suite with a wrong volume is a failure.
3. **No hand-waving.** Never dismiss a failing test or wrong geometry as
   "pre-existing" or "tolerance noise" without root-causing it.
4. **Parallel by default.** Isolated git worktrees + per-instance compose/ports for
   disjoint items. Serial is the exception.
5. **Converge.** Drive the current ROADMAP phase to done, then polish. Work
   that flips a ❌ row on the VISION.md scorecard outranks new pillars.
6. **Keep docs honest** (below) and **never push a red build.**

## Design mandate — STANDING FOUNDER PRIORITY (UI/UX)

Frontend design is a first-class product goal, not polish. CAD tools are where
engineers live all day; ours must look and feel **premium, distinctive, and
intentional**, never templated.

**Flow is the first rule** (founder directive 2026-08-01). Judge every surface
by what the user does NEXT. People try us to escape Fusion's licensing, cost
and lock-in, and they only STAY if modelling does not cost them time, so flow
is the retention mechanic (why: #flow-directive). Each of these tests is a
defect when it fails:

- **The next step is visible from the current state.** A solved sketch's likely
  next action is extrude: present, with the profile pre-selected, not hunted
  for in a toolbar. The tool proposes, the user disposes.
- **Direct manipulation beats forms.** The drag handle is primary and the
  numeric field is the precision fallback. *Product state, last measured
  2026-09-16 at `93733b2`:* the extrude, fillet, shell, datum and both pattern
  gauges have handles a real mouse drag drives. No gauge has had a touch pass,
  and hole has no gauge (CRAFT-9c). **This bullet is a claim about the
  product. Re-measure it before quoting it in a brief, and correct it HERE.**
  (why: #extrude-handle-claims)
- **Capture intent where it forms.** Dimensions are typed while drawing (FB-16),
  not recovered by re-selecting geometry later.
- **No dead ends, no ambiguous exits.** A key that sometimes saves and
  sometimes discards (FB-13) makes people hesitate at every step.

Every founder report on 2026-08-01 (FB-1..FB-19) was a flow failure: the
capability was there and unreachable. Catch that class BEFORE the founder does.

Standing rules:

1. **Always use the `frontend-design` skill** (`.claude/skills/frontend-design/`)
   for ANY UI work, first. It sets or extends the token system (palette / type /
   layout / **one signature element**), avoids the AI-default looks, and
   spends boldness in one place.
2. **Design system first.** `packages/design` (tokens + primitives + fonts) is
   the single source of truth; screens compose primitives. Fix the primitive,
   never the instance. Tailwind preset for the DOM, TS token constants for the
   WebGL viewport: one palette, two renderers.
3. **The viewport is the hero.** Chrome recedes. Panels, trees and toolbars are
   quiet, dense, legible, keyboard-first precision instruments.
3a. **Tool-grade viewport, benchmarked against Fusion 360 / Plasticity**
   (founder recalibration 2026-07-16; the bar is *feels like a modeling tool*,
   not "premium dashboard"). The grid reads to the horizon, the background has
   atmosphere, and bodies get studio shading (matcap/env), never debug-gray. A
   ViewCube/gizmo plus home/iso/ortho snaps are table stakes. **Every chrome
   element is functional**: wire a decorative tile or readout, or delete it.
   Judge screenshots side-by-side against a Fusion/Plasticity reference.
4. **Show, don't tell.** UI changes ship with before/after screenshots
   (desktop + small-laptop widths), and **the orchestrator SENDS them to the
   founder with the file-send tool**. A PNG the founder never sees does not
   count (founder directive 2026-07-23). The capture is also a GATE. When a
   change alters drawn geometry, look at the pair before believing the suite,
   because it is the only check that asks "is the thing legible?"
   (why: #screenshot-gate)
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
services/gateway    FastAPI: auth, REST aggregation, geometry/document proxy
services/geometry   OCCT workers: feature eval, tessellation, export (stateless)
services/documents  Parts/assemblies, feature trees, versioning (Postgres)
packages/py-kit     Shared Python service kit (config, logging, health, queue, errors)
packages/contracts  Generated OpenAPI schemas (committed; CI checks drift)
packages/ts-client  Generated TypeScript client (never hand-edited)
packages/design     Design system: tokens (Tailwind preset + TS constants),
                    UI primitives, fonts (source-only; RESEARCH §5)
deploy/             Docker/Helm assets
docs/               VISION, RESEARCH, ROADMAP, BACKLOG, COMPETITIVE, LESSONS, audits, QA reviews
.claude/            Agents, skills, workflows, PROTOCOL, ORCHESTRATOR
```

## DRY — NON-NEGOTIABLE

WET code is a defect class here, reviewed as such:

- **One source of truth for types:** pydantic models → generated OpenAPI
  (`packages/contracts`) → generated TS client (`packages/ts-client`).
  Hand-written duplicates of API types, in Python or TS, are rejected in
  review. Regenerate with `just gen`; CI fails on drift.
- **Cross-service boilerplate lives in `py-kit` once:** config, logging,
  health/readiness, error envelope, queue plumbing. If you're copying code
  between services, stop and move it to `py-kit`.
- **Frontend primitives:** `apps/web` composes `packages/design` and never
  restyles raw elements. The r3f viewport reads the SAME tokens
  (selection/hover/grid/background); no hex value is duplicated between DOM
  and WebGL.
- DRY ≠ premature abstraction: extract on the second real use, not the first
  imagined one.

## Service boundaries (enforced in review)

- Only `services/geometry` imports OCP/build123d. No kernel types cross a
  service boundary; meshes/exports go to object storage, referenced by ID.
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
just gen-verify     # same, but generated from the INDEX — run this before
                    # committing a schema change while agents run in parallel
just e2e            # geometry gates (goldens + STEP round-trip) + Playwright suite;
                    # boots geometry/gateway itself (PID-tracked, cleaned up)
docker compose up -d --build   # full stack (use `just dev` for dev with hot reload)
```

Keep this section true as targets change.

## Conventions

- Strict typing both sides: pyright-clean Python (no untyped defs in
  services/packages), strict TypeScript (no `any` without justification).
- DB changes via migrations only (alembic), never ad-hoc SQL.
- Geometry tolerances: linear 1e-7 m kernel-side; golden-suite assertions use
  documented per-model tolerances, never ad-hoc epsilons.
- API: REST, versioned under `/api/v1`; error envelope from `py-kit`.
- Conventional-commit messages; one logical item per commit.
- Develop on the current `claude/*` branch; never push to `main` without
  explicit permission.

## Docs in sync — NON-NEGOTIABLE

Stale docs are a defect (see `docs/AUTONOMOUS-LOOP.md`). (why: #doc-tick)

- **Every commit that lands a feature/fix carries its doc tick, EITHER in the
  same commit (`docs/ROADMAP.md` + `docs/BACKLOG.md`) OR as a
  `Doc-tick: groomer` trailer.** The trailer is a DEBT the orchestrator owes
  before the batch closes, not an exemption:
  · a builder in a worktree uses the trailer and never races for the board;
  · a lone committer touching no shared doc may still tick in place;
  · **the orchestrator dispatches the `backlog-groomer` before the batch
    ends**, and a batch is not done while any trailer is unreconciled;
  · the "Current focus" line in `docs/ROADMAP.md` is true at every batch
    boundary.
  To check whether the convention is working, count the commits since the
  last `docs(board)` commit. Do not read the trailers.
- `docs/ROADMAP.md` is the source of truth for "what phase are we in"; its
  status markers and "Current focus" line must always match `git log`. Every
  groom pass reconciles ROADMAP + BACKLOG against git history.

## Definition of done

**Any change** = builds + lint/typecheck + unit tests green + geometry gates
green (when kernel-adjacent) + e2e green (when user-facing) + doc tick (in the
commit or via `Doc-tick: groomer`) + committed & pushed + **CI green on the
pushed commit, in all three workflows**. For new capabilities, add
scripting/MCP exposure where sensible (or an explicit "not agent-appropriate"
note) once Phase 5 lands the surface.

- **Local gates are not the CI gate.** Some failure classes are invisible to
  `just lint && just test && just e2e`. (why: #ci-local-gates)
- **Every commit must be green on its own.** A required-field change and its
  callers belong in ONE commit, even across agent territories.
- Only the orchestrator reads CI (api.github.com is denied to subagents);
  procedure: [.claude/ORCHESTRATOR.md#ci](./.claude/ORCHESTRATOR.md#ci)

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
`frontend-qa` spot-check) → doc tick → commit. `.claude/workflows/`
orchestrates this; `autonomous-dev-loop` chains batches on completion. There
is no cron and no watchdog; see `docs/LOOP-MECHANISMS.md`.

## Orchestration rules

(why: #dispatch-not-do, #staging-protocol)

- **Build in worktrees** (`isolation: 'worktree'`) with explicitly disjoint
  territories. Never edit, revert or commit another agent's in-flight files.
- **Doc edits are the LAST step, staged and committed in the same turn.**
  Never leave ROADMAP/BACKLOG edits unstaged across other tool calls.
  Serialize the doc writers.
- **Staging is perishable.** Never `git add -A`, and never run `git add` and
  `git commit` in one command. Read `git diff --cached` IN FULL (hunks, not
  `--name-only`) right before `git commit`. If foreign text was swept into a
  pushed commit, annotate the record; do not rewrite history.
  (why: #add-and-commit, #sweep-source-files)
- **In a worktree, stage whole files and never use
  `scripts/stage-doc-hunks.py`.** It has failed silently five times, and there
  are no foreign hunks to protect.
- **In the shared checkout,** follow ORCHESTRATOR.md §4 "Committing in the
  shared checkout". (why: #marker-ids, #update-ref, #stop-hook)
- **After a batch,** `git rev-list --count origin/<branch>..<worktree-branch>`
  must be 0 for every worktree branch. **After a container restart,**
  `git fetch && git reset --hard origin/<branch>` before reading anything, and
  trust `git ls-remote` over the local ref. (why: #worktree-push, #worktree-seed)
- **Liveness.** On every wakeup, check in-flight agents' output mtimes. More
  than 30 min stale without a known long gate means investigate, reap, and
  relaunch. A dead agent's work is preserved and reconciled, never reverted.
- **Verify before trusting:** re-run a targeted slice of a completed agent's
  gates. **Run gates in the foreground**, and never end a turn waiting on your
  own backgrounded build.
- **Founder updates are results-first:** what shipped + evidence (numbers,
  screenshots), then what's running, then what's next, proactively at
  milestones.

## Token economy (founder priority 2026-07-10 — quality-neutral savings only)

Spend tokens where quality lives (builders, reviewers, geometry QA):

- **Model tiers:** groomer, vision-steward and oss-curator run on `model: sonnet`,
  and doc-syncer on `haiku`. Never downgrade a role that gates correctness or
  security.
- **Lean briefs** are TASK / TERRITORY / PORTS / BRANCH and point at the
  BACKLOG item's acceptance criteria. Rules go in PROTOCOL.md, not in briefs.
- **Scoped reading and targeted verification.** Read only the doc *sections*
  you need. Run the full sweep (`just lint && just test && just e2e`) once per
  batch end.
- **Lean shared docs:** BACKLOG changelog entries ≤3 lines, older ones pruned
  into CHANGELOG.md each groom pass, and Done archives at one line per item.
- **Right-size reports:** evidence tails and decisions, not narration.
  Screenshots > prose.

## Gates and evidence

These add to PROTOCOL.md §8.

- **Can this gate fail? Show it failing.** Inject a mutation at the START of
  the verdict block, upstream of every guard. (why: #negative-control-downstream)
- **Census each declared root, and refuse when any contributes zero.** A
  global count floor only catches total collapse. Keep the roots in one named
  constant. (why: #count-floor)
- **Derive the EXPECTED set independently.** A gate that reads the same list as
  the code can only prove the list is self-consistent. (why: #absent-set)
- **Audit a recurring defect class by its question** ("what does this gate do
  when it examines nothing?"), not by the last instance's shape.
  (why: #audit-by-question)
- **When existing gates reject a new fixture,** they probably share a blind
  assumption. Read the rejection before "fixing" the fixture.
  (why: #fixture-rejected)
- **Bisects:** the green end must be a commit you SAW pass. Read the exact
  expected-vs-received before blaming "environment". If the diff cannot reach
  the failure, diff the failing test across the two commits; red at N+1 only
  proves the failure became observable there. (why: #bisect-green-end, #sharded-bisect)
- **Instrument a slow spec before optimising it** (the cost is usually round
  trips). When you remove work, name any accidental settle it was providing
  (`waitForFrames`). (why: #accidental-settle)
- **Verify a bulk deletion by conserving rare tokens:** every backtick token
  and every word that occurs ≤2 times in the original must survive somewhere
  in the rewrite. Do not rely on reading the diff.
  (why: #rare-token-conservation)

## Environment recipes

Stack and process rules are in PROTOCOL.md §7 and gates in §6; these are the
rest. **After >15 minutes lost to an environment quirk, add a 1-3 line rule
here and the story to `docs/LESSONS.md`, in the fix's commit.** (why: #env-intro)

- **Python / tools:** `uv python install` is 403, so use the system
  `/usr/bin/python3.10`–`3.13` (`uv sync` picks 3.12). PyPI and npm are direct.
  Install `just` with `uv tool install rust-just`. OCP/OCCT wheels are large,
  so CI caches the uv environment keyed on the lockfile. (why: #python-and-just)
- **Egress:** github.com release assets and distro source hosts are 403, but
  `git clone` over HTTPS, `raw.githubusercontent.com`, `archive.ubuntu.com`,
  `files.pythonhosted.org` and `conda.anaconda.org` work. Try another protocol
  before calling bytes unfetchable, assert on size (zero-byte 200s happen), and
  prefer index URLs. See `docs/LICENSING.md` §7.5. (why: #egress-map)
- **No image build here** (the Docker blob CDN is 403).
  `scripts/check-build-context.py` (in `just lint`) gates `.dockerignore`
  against every Dockerfile COPY. A gate that re-implements an absent tool is
  cross-checked against the real one and ships a `--self-test`.
  (why: #build-context-gate)
- **Native boot:** copy the schema step from `scripts/e2e.sh`
  (`metadata.create_all` into per-service `sqlite+aiosqlite:///` files via
  `POSTGRES_URL`). Never run alembic against SQLite, and `rm -f` your own files
  first, because `create_all` does not migrate. Geometry uses `--workers 1`
  with no `S3_URL`. The gateway uses `LOFT_ENV=dev`, `GEOMETRY_URL` and
  `DOCUMENTS_URL`, with no `REDIS_URL`. Then run
  `scripts/smoke-healthz.sh <port>`. e2e and founder screenshots run here, not
  only in CI. (why: #native-boot)
- **No IPv6 loopback here; CI is dual-stack.** Bind literal `--host 127.0.0.1`,
  and when you cannot reproduce a diagnosis locally, ship the probe with the
  fix. (why: #ipv6-loopback)
- **Before a batch-end `just e2e`,** kill the shared listeners by port
  (`lsof -ti tcp:<port> -sTCP:LISTEN` on 8000/8001/8002/5173), because it
  reuses stale ones. Run it in a QUIET window: a red run under load is
  unconfirmed, and a failure point that moves is a flake tell.
  (why: #stale-uvicorns, #stale-vite-teardown, #quiet-window)
- **Scratch placement:** Playwright wipes `apps/web/test-results/`. An
  isolated Playwright config goes in
  `apps/web/node_modules/.vp1a/<name>.config.mjs` (it must be `.mjs`, and it
  needs its own `baseURL`). `prettier --check .` walks the filesystem, so never
  leave dumps at the repo root. A temp spec in `apps/web/e2e/` is formatted at
  once and deleted the same turn. (why: #test-results-wiped, #gen-verify)
- **Workflows and job logs you write:** `scripts/check-workflow-contexts.py`
  grades `env:` expressions only, so other workflow edits are unverifiable
  until the run. Use `$RUNNER_TEMP`, not `${{ runner.temp }}`, inside `run:`.
  A log you own ends with a short verdict that does not count a `test.fail()`
  case as a failure. Never disable `geometry-minio-smoke`.
  (why: #ci-workflow-refused, #pytest-verdict-last, #ci-minio-withdrawn)
- **Formatting:** committed JSON/MD/YAML, golden JSON included, passes
  `prettier --check`. Prefer ASCII (`x`, `-`, `<=`) in code and tests.
  (why: #lint-gate)
- **Founder screenshots are refresh-on-demand:**
  `UPDATE_SCREENSHOTS=1 pnpm --filter @loft/web e2e`
  (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` for `exec playwright test`).
  Specs import `test`/`expect` from `./fixtures`, and `reducedMotion` stays off.
  (why: #founder-screenshots)
- **pytest:** conftest env (e.g. `LOFT_ENV`) leaks across the whole-repo run,
  so tests that depend on it `monkeypatch` it explicitly. Put a verdict in
  `pytest_unconfigure`. Never add `-q` on the CLI: `addopts` already has it,
  and `-qq` deletes the summary line.
  (why: #conftest-env-leak, #pytest-verdict-last, #pytest-qq)
- **FastAPI route walks** use `fastapi.routing.iter_route_contexts` and assert
  the count walked. (why: #fastapi-routes)
- **three.js type checks** use the flags (`isPerspectiveCamera`, `isMesh`, …),
  not `instanceof`. The app bundle is fine, but vitest loads a second CJS copy
  of three. `instanceof` against builtins is fine. (why: #instanceof-dual-builds)
- **Tailwind:** an unknown utility emits nothing (the spacing scale ends at
  12), so an element measuring 0, or a `<canvas>` at `300x150`, is un-styled.
  (why: #force-true-zero-area, #tailwind-preset-restart, #tailwind-probe)
- **Build-time checks run as the runtime user** (after `USER`). A validator may
  also write: `nginx -t` creates the pid file. (why: #nginx-pid)
- Swapping a vendored `.so` without touching `.venv`: see #runpath-swap.
