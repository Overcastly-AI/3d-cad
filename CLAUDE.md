# CLAUDE.md — Loft (working name)

Guidance for Claude Code (and other AI agents) working in this repository.

---

## READ THIS BEFORE YOUR FIRST TOOL CALL

**If you are the ORCHESTRATOR, open
[`.claude/ORCHESTRATOR.md`](./.claude/ORCHESTRATOR.md) now and follow it.**
It is short. This file is the reference manual; that one is the procedure.

It is placed here, at line 1, because the previous pointer to it sat at line
338 of a 1017-line file and the process it describes was consequently not
followed. The founder's summary of what that cost: *"none of the agents are
being used in the project. You are constantly over writing files and then
wasting tokens trying to fix and racing before the next cron job kicks off."*

The four rules, so they are in your context even if you read nothing else:

1. **You dispatch and integrate. You do not do the org's job.** The
   `backlog-groomer` owns `docs/BACKLOG.md`. The auditors own the audit docs.
   Builders write code; reviewers review; QA exercises the real app. **If you
   are editing the backlog yourself, you have already gone wrong.**
2. **Use the agents.** There are fourteen in `.claude/agents/`. On 2026-08-14
   an audit found eight had never been invoked — the entire direction layer was
   dead and the orchestrator was doing it by hand, in the most expensive context
   in the system.
3. **Builders get their own worktree** (`isolation: 'worktree'`). A shared
   checkout is the root of every overwrite, and of the staging tool that has
   failed silently three times.
4. **Reading CI is yours alone** — `api.github.com` is denied to every
   subagent. Agents push and stop; you read the run and relay failures back.

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
and intentional** — never templated.

**FLOW IS THE FIRST RULE (founder directive 2026-08-01: "Flow is critical for
users. Think about it as you build. How should we direct the user? Hopefully in
a way to leave fusion and go OS").** Judge every surface by what the user does
NEXT, not by whether the current screen is correct in isolation. The strategic
reasoning, because it changes priorities: people leave Fusion for licensing,
cost and cloud lock-in — that gets them to TRY us. They only STAY if modelling
does not cost them time. Nobody trades muscle memory for a philosophy. So flow
is the RETENTION mechanic, and feature parity without it produces a tool people
admire and do not use. Four concrete tests, each one a defect when it fails:

- **The next step is visible from the current state.** A solved sketch's likely
  next action is extrude — present, with the profile pre-selected, not hunted
  for in a toolbar. The tool proposes, the user disposes.
- **Direct manipulation beats forms.** Fusion's extrude is a draggable arrow;
  the numeric field is the precision fallback. Ours is a form with no handle at
  all — the single biggest "does not feel like a modeling tool" gap we have,
  bigger than any missing feature.
- **Capture intent where it forms, not afterwards.** Dimensions typed while
  drawing (FB-16), not recovered by re-selecting geometry later.
- **No dead ends, no ambiguous exits.** A key that sometimes saves and sometimes
  discards (FB-13) does more than risk work: it makes people hesitate at every
  step, which is what actually destroys flow.

Every founder report on 2026-08-01 (FB-1..FB-19) was a flow failure, not a
missing capability — the capability was almost always there and unreachable.
That is the class of defect this rule exists to catch BEFORE the founder does.

Standing rules:

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
   **"Surfaced" means the orchestrator SENDS the screenshots to the founder
   (the file-send tool), not merely generates them into `docs/screenshots/`.**
   Every UI change → pass the before/after shots to the founder in chat;
   generating a PNG the founder never sees does not count (founder directive
   2026-07-23).
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
just gen-verify     # same, but generated from the INDEX — run this before
                    # committing a schema change while agents run in parallel
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
  user-facing) + ROADMAP/BACKLOG ticked + committed & pushed + **CI green on
  the pushed commit**. For new capabilities: scripting/MCP exposure where
  sensible (or an explicit "not agent-appropriate" note) once Phase 5 lands
  the surface.
- **LOCAL GATES ARE NOT THE CI GATE — check GitHub Actions after every push
  (orchestrator duty).** Learned the hard way 2026-07-25: the founder had to
  tell us "none of the CI tests are passing" after CI had been red for
  **days** while every batch was being certified green locally. Two
  independent causes, both invisible to `just lint && just test && just e2e`:
  (a) `geometry-minio-smoke` had been failing since the job landed —
  `docker compose up -d --wait minio minio-init` names a ONE-SHOT in a
  `--wait` list, and `--wait` waits for running|healthy and treats a
  container that EXITS as a failure, so the step returned 1 the instant the
  bucket bootstrap *succeeded*; and the Docker registry is blocked in this
  container, so no local run could ever have exercised it. (b) A required
  DTO field (`ViewCreate.auto_place`) landed in one agent's commit while the
  web callers were fixed in a different agent's later commit, so the
  intermediate commit was typecheck-red in CI even though the tip was green.
  Rules: after pushing, **read the run for that SHA** (GitHub MCP:
  `actions_list` → `list_workflow_runs` filtered by branch, then
  `get_job_logs` with `failed_only: true`); treat `cancelled` as "superseded,
  look at the newer run," not as pass; and **every commit must be green on
  its own**, so a required-field change and its callers belong in ONE commit
  even when that crosses agent territories.
- **Only the ORCHESTRATOR can read CI — subagents cannot. Budget the relay
  into the brief.** A subagent has no `gh`, no GitHub MCP in its toolset, and
  `api.github.com` is policy-denied for its session (`403 GitHub access is
  not enabled for this session`) — same policy-denial class as the blocked
  docker registry, so there is nothing to route around. A brief that ends
  "push and then read the run" therefore dead-ends *after* the agent has done
  the work. Either (a) tell the agent to push and stop, and the orchestrator
  reads the run and relays `get_job_logs` output back via SendMessage so the
  agent can iterate, or (b) keep CI-verified work in the orchestrator's own
  hands. Do NOT write briefs that assume a subagent can self-verify CI.
- **CI can ONLY be read through the GitHub MCP tools — never a bash poll, not
  even in the orchestrator's own session.** `api.github.com` is policy-denied
  from `Bash` here for the orchestrator too (the bullet above is about
  subagents, but the block is not subagent-specific), so the natural instinct
  — arm a `Monitor` that curls the runs endpoint until the conclusion lands —
  **cannot work**: the monitor fires once with the poll error and exits, which
  reads like "still running" if you aren't watching for it. Same for
  `Bash(run_in_background)`. Consequence: **waiting on CI is turn-based.** Push,
  then read the run with `actions_list` → `list_workflow_runs` (filter by
  branch) or `actions_get` → `get_workflow_run` on a known run id, and re-read
  it on a later turn; there is no way to be woken by a CI transition. Two
  practical notes: (a) `list_workflow_runs` returns ~430 KB and blows the tool
  limit — it gets spilled to a file, so parse that file with `python3 -c` and
  print only `head_sha`/`status`/`conclusion` rather than trying to read it.
  **`per_page` is IGNORED** — asking for 1 still returns 30 runs and the same
  ~430 KB, so do not bother trying to trim the payload that way; the spill +
  parse is the only cheap path;
  (b) `get_workflow_run` on ONE id is small and is the cheap way to re-check a
  known run.
- **FIXED 2026-07-30 — `cancel-in-progress` is now PR-only, so a branch run
  that has STARTED is no longer killed by the next push. MEASURED, with one
  caveat below.** History, because the reasoning matters: the
  concurrency group is keyed on the ref, and with blanket cancellation pushing
  commit B ~3 min after A left A's run `cancelled` — which by the rule above is
  NOT a pass, so A shipped CI-unverified with nothing wrong with it. It hit
  three commits in a row (`6c9c432`, `8f387fc`, nearly `fe2e5cb`), including
  the commit that first *documented* the trap, and the exposure scales with the
  number of agents pushing in parallel — precisely when per-commit signal
  matters most. Blanket cancellation and "every commit green on its own" cannot
  both hold, so cancellation now applies only to `pull_request` (where just the
  head matters for merge). Two things follow: (a) don't "fix" a red-looking
  board by re-enabling it; (b) a `cancelled` run on a branch push is now a real
  anomaly worth investigating, not the routine noise it used to be.
  NB a descendant's green run does verify the *tree* of its ancestors, so a
  cancelled ancestor whose child is green is not an unknown build — it is an
  unverified *commit*. Say which of the two you mean.
  **SUPERSEDED 2026-07-30 by a per-SHA group — read this caveat as the reason
  why.** The PR-only `cancel-in-progress` alone did NOT save a run that had not
  STARTED yet. Evidence: with the fix live, `5de225c`'s run stayed
  `in_progress` across a later push (the old config would have killed it
  instantly) — but `60ac962` and `cb0dcd0`, also pushed with the fix in their own
  trees, still came back `cancelled`. The difference is that those two were
  superseded before getting a runner slot: a concurrency group admits one running
  plus one *pending* run, and a newer arrival evicts the pending one regardless of
  `cancel-in-progress`, which only governs runs already holding a slot. So under
  runner contention — which is exactly when several agents are pushing — rapid
  back-to-back pushes can still cost the middle commit its run. Practical rule:
  the fix removed the routine case but not the mechanism. Under four agents
  pushing it became the NORM, not an edge: **5 of 8 consecutive runs came back
  `cancelled`**, including `5794b48` — the fix for the very lint failure an audit
  had just flagged — so the rule was unenforceable exactly when parallelism made
  it most valuable. Real fix: the push group is now keyed on `github.sha`
  (`format('ci-sha-{0}', github.sha)`), giving every commit its own group that
  nothing can evict; PRs keep a ref-keyed group so a superseded PR push still
  cancels. It costs runner minutes, which is the price of the rule. Consequence:
  a `cancelled` run on a branch push is now genuinely anomalous — investigate it
  rather than shrugging.
- **A COMMIT PUSHED IN THE MIDDLE OF A MULTI-COMMIT PUSH GETS NO RUN AT ALL —
  not a cancelled one, NOTHING — so "every commit green on its own" has a hole
  the per-SHA concurrency fix does not touch.** GitHub fires ONE workflow run per
  push *event*, keyed to the push's head commit; every commit between the old tip
  and the new one is simply never built. This is invisible in a way eviction is
  not: a `cancelled` run is at least a row you can see and question, whereas an
  unbuilt commit leaves no row, so the board looks complete. Measured 2026-08-01:
  `3065813` and `3cf6650` were committed 69 s apart and pushed together, and
  `3065813` has ZERO runs across all three workflows while `3cf6650` has three —
  and `3065813` touched `apps/web/e2e/**`, so it was not a paths-ignore skip.
  Two consequences. (a) **Push each commit separately** when you want per-commit
  evidence — the per-SHA group means back-to-back pushes no longer cost each
  other their runs, so the reason to batch is gone. (b) When auditing, do not
  reason from the runs list alone: it enumerates PUSHES, not commits. Cross-check
  against `git log` and treat a commit with no row as UNVERIFIED, exactly like a
  cancelled one. (Its descendant's green run still verifies the *tree*, never the
  intermediate *commit* — the same distinction the bullet above insists on.)
- **`cancelled` HAS TWO CAUSES AND GITHUB USES THE SAME WORD FOR BOTH** — a
  concurrency eviction, and a job hitting `timeout-minutes`. Discriminate by
  DURATION and by the sibling jobs. Seen 2026-07-30: three runs read `cancelled`
  *after* the per-SHA fix and I nearly concluded the fix had failed; in fact the
  `python` job's Pytest step ran **14m31s** and the job was killed at **15m16s**
  against a 15-minute ceiling, while the other four jobs all passed. An eviction
  kills a run EARLY and takes ALL its jobs with it; a timeout kills ONE job at
  almost exactly the configured limit and leaves its siblings green. So read
  `list_workflow_jobs` for the run and look at per-job conclusions and step
  durations before naming a cause — the run-level `conclusion` alone cannot tell
  you which happened. (The python job is now 30 minutes. The suite is ~2958 tests
  dominated by OCCT geometry and grows with every verb and golden, so expect to
  revisit it; sharding is the next lever if 30 gets tight.)
- **A suspiciously FAST green deserves the same scrutiny as a red.** The
  usual cause is a job that skipped its work, and `conclusion: success` is
  emitted when every job is skipped. Discriminate by reading the log for
  evidence the work actually happened (2026-07-25: the first-ever deploy-path
  run passed in 86s where ~20 min was expected — real, and the proof was the
  teardown naming six actual containers; a no-op job has nothing to remove).
  Prefer asserting on a side effect only real execution produces.

## Work as a dev team

**ORCHESTRATOR: READ [`.claude/ORCHESTRATOR.md`](./.claude/ORCHESTRATOR.md)
FIRST, EVERY SESSION.** It is the playbook you follow — what is yours, what
belongs to an agent, the audit -> groom -> build -> integrate loop, and the
anti-patterns with the evidence that earned them. The short version: you
dispatch and integrate; you do not write the board, run the audits, or build.

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
on completion. There is no cron and no watchdog — see `docs/LOOP-MECHANISMS.md`
for what wakes the loop and what each mechanism survives.

## Multi-agent orchestration protocol

**READ THIS FIRST — most of the rules below exist because we were not doing the
two things at the top of this list, and they become far less load-bearing once
we are.**

- **THE ORCHESTRATOR DISPATCHES AND INTEGRATES. IT DOES NOT DO THE ORG'S JOB.**
  Audited 2026-08-14 after the founder said "none of the agents are being used":
  eight of the fourteen agents in `.claude/agents/` had never been invoked, and
  the orchestrator had been writing `docs/BACKLOG.md` ITSELF — `file CI-4`,
  `file REV-1..REV-5`, `file QA7-1` are all orchestrator commits. That is the
  `backlog-groomer`'s entire job, performed in the most expensive context in the
  system. Every symptom followed from it: two classes of writer on the shared
  docs (hence overwrites, hence the staging tool below), audits done by hand
  instead of by `product-auditor`/`engineering-auditor`, and a cron racing its
  own slices. **The groomer owns the board. The auditors own the audit docs. The
  builders own their code. The orchestrator hands out tickets, integrates green
  branches, and reads CI — which is the one thing no subagent can do.**
- **BUILD IN WORKTREES.** Give every parallel builder `isolation: 'worktree'`.
  We documented this at `.claude/workflows/autonomous-dev-loop.md` for weeks and
  never did it, and the cost is most of this section: a shared index is the only
  reason `git add` can sweep a colleague, the only reason a stale `read-tree`
  can revert one, and the only reason `stage-doc-hunks.py` exists. Next-Lane
  runs the same loop with worktrees and has no equivalent script at all.
- **DOC EDITS ARE THE LAST STEP, STAGED AND COMMITTED IN THE SAME TURN.** This
  is Next-Lane's actual mitigation for the shared-doc race, and it is cheaper
  and more reliable than ours. Never leave `docs/ROADMAP.md` / `docs/BACKLOG.md`
  edits unstaged across other tool calls — that window is the whole hazard. When
  several agents must touch the same docs, serialize the doc-writers or give one
  a worktree. `scripts/stage-doc-hunks.py` is now a FALLBACK for the
  unavoidable shared-tree case, not the default path: it is 905 lines, it has
  failed silently three times in production (swept a colleague's entry;
  relocated the author's own entry to the end of the file; truncated an entry to
  7 lines of 31 while reporting "left 0 hunk(s) unstaged"), and every one of
  those failures was a cost of sharing a tree rather than a reason to trust the
  tool. Read `git diff --cached` in full before every commit regardless.
- **File territories.** Parallel agents get explicitly disjoint territories in
  their briefs (e.g. one holds `services/geometry/**`, another `apps/web/**`).
  Never edit, revert, or commit another agent's in-flight files. Foreign
  uncommitted work in shared files: build alongside, stage only your hunks.
- **Commit protocol:** stage your own files explicitly — never `git add -A`.
  **And for the HIGH-TRAFFIC SHARED DOCS (`docs/ROADMAP.md`, `docs/BACKLOG.md`),
  `git add <file>` is not "explicit" enough — stage HUNKS.** Every agent is
  required to tick both in the same commit, so they are nearly always dirty with
  somebody else's in-flight text; `git add docs/BACKLOG.md` then silently
  captures it. Seen 2026-07-30: an orchestrator commit about an unrelated test
  gate (`33b1b5a`) carried three P3 items another agent had just filed, so the
  commit message described none of its own contents and the authorship in history
  is wrong. Nothing was lost, which is exactly why it is easy to miss. Use a
  filtered `git apply --cached` (or `git add -p`) for these two files, and if you
  find you have already swept foreign text, annotate the record rather than
  rewriting shared history that other agents have already rebased onto.
  **Use `python3 scripts/stage-doc-hunks.py <file> "<marker>"`** — it stages only
  hunks that ADD a line containing your marker and leaves the rest unstaged for
  their author. It exists because this rule was broken TWICE in one day, the
  second time by the person who wrote it: the correct path was fiddly and
  `git add <file>` is four words, and under load the cheap path wins. A rule that
  loses to convenience is not a control; make the correct path the easy one.
  **It filters at LINE granularity, and it has to.** The first version matched
  whole hunks, which silently swept a colleague's entry whenever theirs sat
  beside yours — git merges changes within its context window into ONE hunk, and
  a blank line between two appended entries is NOT enough to separate them
  (measured). It reported "left 1 hunk(s) unstaged for their author" while doing
  it, which is worse than failing. Note `git add -p` is NOT a fallback here:
  interactive git is unavailable in this container.
  **And that line-granularity filtering then MIS-PLACED the author's own entry —
  the failure nobody was watching for, because everyone was watching the
  colleague's text.** Fixed 2026-08-01, found by the dogfooding pass, reproduced
  deterministically. The tool emits `--unidiff-zero` sub-hunks and DROPS the
  colleague's added lines from the patch, but it was numbering the new side by
  walking the full working-tree diff — which counts those dropped lines. So every
  sub-hunk after a colleague's entry carried a `+b` too large by exactly the
  number of lines dropped, and `git apply` inserted the text somewhere else: in
  the measured case `@@ -5,0 +9,3` where `+6` was right, landing the author's
  entry at the END of the file, after an unrelated item, blank-line separator
  gone — while printing "staged 1 hunk(s) … left 0 hunk(s) unstaged". The
  colleague's text was untouched, which is why the existing guard (does it sweep
  a neighbour?) sailed past it. `+b` is now DERIVED as
  `run_old_anchor + 1 + emitted`, a function of what the patch actually contains,
  so it cannot drift from it. Two general lessons: **a tool that guards commits
  needs its own guard** — `python3 scripts/stage-doc-hunks.py --self-test` builds
  a throwaway repo with a colleague's entry directly above yours and compares
  `git show :FILE` BYTE-FOR-BYTE, because asserting the exit code would have
  passed all along; and **check the staged tree, not the staging report** —
  `git show :<file>` after staging a shared doc, not just `git diff --cached`.
  **AND THE SELF-TEST I ADDED THAT MORNING PASSED WHILE THE TOOL SWEPT A
  COLLEAGUE'S ROADMAP ENTRY THAT AFTERNOON — a fixture in the wrong FORMAT is a
  gate that cannot fail for the reason you care about.** `ENTRY_START` knew list
  items and headings, so it found boundaries in `docs/BACKLOG.md` (`- [ ] …`) and
  none at all in `docs/ROADMAP.md`, whose entries are bold-lead PARAGRAPHS
  (`**QA3-1 CLOSED (…) — …**`). Two adjacent ROADMAP entries therefore read as ONE
  run of added lines, the marker made the whole run "mine", and it staged 31 lines
  where 16 were mine — printing "left 0 hunk(s) unstaged for their author" as it
  did. My self-test used the BACKLOG shape only, so it sailed through. Caught by
  the kernel agent reading `git diff --cached` in full; nothing was lost. Three
  changes, and the second is the one that generalises: (a) `ENTRY_START` learned
  bold-lead paragraphs; (b) a SECOND, independently-derived entry count (added
  lines separated by an added blank line) now cross-checks it, and the tool
  REFUSES when the two disagree rather than guessing — so the next format nobody
  taught it fails loudly instead of eating a neighbour; (c) `--self-test` carries
  BOTH doc shapes, and the negative control is that reverting the regex makes the
  ROADMAP case refuse. Note a post-condition that compares the staged tree
  against what attribution CLAIMED does NOT catch this: a wrong claim verifies
  happily against itself. That is the `gen-check`-measuring-the-wrong-input trap
  wearing different clothes, and the fix is the same — get a second opinion from
  a different derivation, not a louder assertion of the first.
  **AND THE CROSS-CHECK THAT WAS ADDED TO CATCH ALL THIS WAS ONE-DIRECTIONAL, SO
  IT SAT OUT THE NEXT FAILURE.** Fixed 2026-08-11, found by the SEL-6 QA agent.
  The bold-lead alternative from the fix above matched `**` ANYWHERE, so a
  CONTINUATION line opening with a bold run — `**94.8 %**, every answer naming
  the near face`, i.e. how anyone writes a measured result — read as a new entry.
  The marker matched only the text above it, everything below was attributed to a
  colleague who does not exist, and `mine_only_subhunks` dropped it: **7 lines
  staged of a 31-line ROADMAP entry**, reported as `left 0 hunk(s) unstaged for
  their author`. Caught only by reading `git diff --cached` in full. This is the
  MIRROR of the previous defect — that one MISSED a boundary and swept a
  neighbour, this one INVENTED a boundary and truncated the author's own entry —
  and the guard added for the first was written as `blanks > seen`, which is
  blind to `seen > blanks`. It was `seen=2, blanks=1`; `1 > 2` is false; nothing
  fired. Two changes: a bold lead now opens an entry only where an entry CAN
  begin (top of the run, or after a blank line — both docs separate entries that
  way), and the cross-check refuses on ANY disagreement, either direction. The
  general lesson is narrower and sharper than "add a cross-check": **a guard
  written against one failure tends to encode that failure's DIRECTION.** Ask
  what the symmetric mistake looks like and make sure the guard fires on it too.
  Note also that the exit code was 0 throughout — `--self-test` now carries a
  third fixture (`bold-continuation`) and its negative control reproduces the
  defect exactly: exit 0, colleague untouched, tree wrong. Only the byte-for-byte
  `git show :FILE` comparison catches it.
  **When you are ready to commit and ANOTHER agent already has files staged, do
  not touch their index — build your commit against an isolated one.** The
  staging protocol above assumes the index is yours to arrange, and under four
  parallel agents it frequently is not: a `git reset` to clear someone else's
  staged work, or a commit that sweeps it in, are both the same defect (a commit
  whose message describes none of its own contents). `GIT_INDEX_FILE` gives you a
  private index for the duration:
  ```bash
  export GIT_INDEX_FILE=$(mktemp -u /tmp/idx.XXXX)
  git read-tree HEAD                     # start from HEAD, not from their index
  git add <your files only>              # stage-doc-hunks.py still applies to ROADMAP/BACKLOG
  git commit -m "…"                      # commits YOUR tree; their index is untouched
  unset GIT_INDEX_FILE
  ```
  Used first on 2026-07-31 by the perf agent, which found ~40 of a sibling's
  files staged when its own work was ready; nothing of theirs was swept and their
  commit landed as its parent. Verify afterwards with `git show --stat HEAD` that
  the commit contains only your paths — the isolated index protects their work,
  not you from your own `git add`.
  **AND `git read-tree HEAD` SNAPSHOTS HEAD AT THAT MOMENT — if a sibling commits
  before you do, your commit REVERTS THEIRS.** This is the recipe's own trap and
  it bit within hours of the recipe landing: the ops agent read-tree'd, worked,
  and committed; a sibling had committed in between, so its tree carried the
  PRE-sibling content and its commit silently deleted `CLAUDE.md`'s and
  `docs/ARCHITECTURE.md`'s changes plus three screenshots. It was caught only
  because the agent ran `git show --stat HEAD` before pushing and saw deletions
  it never made. Nothing reached the remote, which is the good outcome and also
  why this is easy to miss — a `git commit` that reverts a colleague reports
  nothing unusual. Two rules: pin the base explicitly rather than by name
  (`base=$(git rev-parse HEAD); git read-tree "$base"`), and immediately before
  committing re-check that `git rev-parse HEAD` still equals `$base` — if it
  moved, re-read-tree from the new HEAD and re-add your paths. Then `git show
  --stat HEAD` and read it for paths you did NOT touch; that check is not
  optional, it is the only thing that catches this.
- **`stage-doc-hunks.py`: a bare item id is NOT a safe marker, because siblings
  cross-reference ids.** Seen 2026-07-31: `stage-doc-hunks.py docs/BACKLOG.md
  "OPS-1"` swept another agent's OBS-1 entry, because THEIR text contained the
  phrase "the same shape as OPS-1". The tool did exactly what it was told; the
  marker was the defect. Use a phrase from your own entry's FIRST line — e.g.
  `"OPS-1 — there was no backup"` rather than `"OPS-1"` — so the match cannot
  land inside somebody else's prose. The tool now prints the entry-start line of
  everything it stages; read that output rather than trusting the count.
- **THE SWEEP IS NOT A DOCS PROBLEM — it happens in SOURCE files too, and there
  the hunk tooling does not apply.** The staging rule names `docs/ROADMAP.md` and
  `docs/BACKLOG.md` because those are the two files every agent is REQUIRED to
  touch. That framing is too narrow: any file two agents happen to edit at once
  has the same hazard, and `git add <one source file>` is just as wholesale as
  `git add <one doc>`. Seen 2026-08-01: the folders agent staged
  `packages/py-kit/src/py_kit/schemas/features.py` while the prefetch agent had
  four uncommitted DTOs in it, so `17404ab` (a folders commit) shipped
  `WarmTreeRequest`/`WarmTreeResult`/`WarmCancelRequest`/`PrefetchRequest`, and
  the prefetch commit that followed contains no py-kit hunk at all. Nothing was
  lost and BOTH commits are green on their own — the models were unreachable from
  any route in the folders tree, so its OpenAPI was unchanged, which is precisely
  why no gate objected. The universal check is cheap and needs no tool:
  **`git diff --cached` and READ IT before every commit.** Not `--name-only` —
  the names looked right here; the hunks were the problem. If a hunk is not
  yours, unstage that path (`git reset -q HEAD -- <path>`), re-add only your own
  changes, and tell the other agent. Annotate rather than rewrite once siblings
  have rebased onto it.
  **AND THEN RESYNC THE DEFAULT INDEX, or your own commit reads as uncommitted.**
  `.git/index` never learns about a commit made through another index, so it keeps
  the PRE-commit blob for every path you just committed and `git status` reports
  them as dirty (`MM <file>`) forever. Caught within minutes of writing this
  recipe: a stop-hook git check flagged an orchestrator commit as unpushed work
  when it was already on the remote. The tell is `git diff HEAD -- <path>` coming
  back EMPTY while `git status` calls the path modified — worktree matches HEAD,
  so the index is the stale party. Fix per path you committed:
  ```bash
  git reset -q HEAD -- <the paths you just committed>   # NOT a bare `git reset`
  ```
  Name the paths. A bare `git reset` would unstage a colleague's work, which is
  the defect this whole technique exists to avoid.
  **AND THE RESYNC ITSELF CAN UNSTAGE A COLLEAGUE — naming the paths is not
  enough when the paths are SHARED.** `git reset -q HEAD -- <paths>` mutates the
  DEFAULT index, and every agent is required to touch `docs/ROADMAP.md` and
  `docs/BACKLOG.md`, so those two paths are almost always in somebody else's
  staging area at the same moment. Seen 2026-08-01: an agent staged its doc hunks,
  a sibling committed through an isolated index and resynced those same two paths,
  and the first agent's hunks were silently unstaged — its commit would have
  landed without its ROADMAP/BACKLOG tick, which is the one thing every commit is
  required to carry. Nothing warns you. That is now THREE distinct ways this
  recipe bites (a stale `read-tree` base reverting a sibling, a marker matching a
  sibling's prose, and this), and the SAME cheap check caught all three:
  **re-read `git diff --cached` immediately before `git commit`, not when you
  staged.** Treat staging as perishable — stage and commit in one tight window
  rather than staging early and doing more work.
  Push with `git push -u origin <branch>`; on rejection `git pull --rebase`
  and retry. Commit only when your gates are green.
- **The stop-hook "there are uncommitted changes, please commit and push" is a
  FALSE POSITIVE whenever agents are in flight, and obeying it literally is the
  sweeping defect above at its worst.** The hook cannot tell your work from four
  colleagues' half-finished work; during a parallel batch the tree is *supposed*
  to be dirty, and "commit and push these changes" would produce one commit
  containing four agents' unfinished slices under a message describing none of
  them. Seen repeatedly on 2026-07-31 with four agents live. The correct response
  is to VERIFY, not to comply: `git diff --cached --name-only` empty (nothing of
  yours staged) and `git log --oneline origin/<branch>..HEAD` empty (nothing of
  yours unpushed) means you are clean and the dirt is theirs. Map the dirty paths
  to territories and say so; do not commit, do not stash, do not revert. Only if
  one of those two checks is non-empty do you actually owe a commit.
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
- **`git push -u origin <branch>` FROM A WORKTREE PUSHES NOTHING AND SAYS
  "Everything up-to-date" — and worktree isolation is MANDATORY for builders, so
  the standing push instruction is wrong for every builder we run.** Found
  2026-08-16 by the backlog-groomer, which noticed its own commit had not landed
  and re-pushed by hand; reproduced deterministically before writing this down.
  Mechanism: a worktree is on its OWN branch (`worktree-agent-<id>`), while the
  shared checkout holds `claude/<name>`. `git push origin <branch>` expands to
  the refspec `<branch>:<branch>`, and the LEFT side is resolved as a local ref —
  so git pushes the MAIN checkout's branch, which is already at the remote tip,
  and truthfully reports it is up to date. Your commit is never mentioned.
  Measured, with a scratch commit in the worktree so HEAD and the ref differed:
  ```
  HEAD                                    ebbaa18
  ref claude/branch-review-development-…  5c7fb48   (the OTHER worktree's branch)
  git push --dry-run -u origin claude/…   -> "Everything up-to-date"
  git push --dry-run origin HEAD:claude/… -> "5c7fb48..ebbaa18  HEAD -> claude/…"
  ```
  Use `git push origin HEAD:<branch>` — pushing the commit you are ON, by value,
  rather than a name that resolves somewhere else — and then VERIFY with
  `git ls-remote origin <branch>` that the remote tip equals `git rev-parse HEAD`.
  Two things generalise. (a) **This failure is silent and success-shaped**: exit
  code 0, a reassuring sentence, and a whole agent run left on the floor; the
  push-succeeded belief is only falsifiable against `ls-remote`, so verify by
  VALUE, never by exit status. It is the zero-byte-200 trap in different clothes.
  (b) A `-u` flag is not a safety net — here it cheerfully offered to set the
  upstream of a branch the agent was not on. Auditing for this is cheap and worth
  doing after any batch: `git rev-list --count origin/<branch>..<worktree-branch>`
  should be 0 for every worktree branch.
- **A freshly-created WORKTREE gives FALSE `prettier --check` and `tsc` failures
  on files you never touched — and they name a COLLEAGUE'S territory, so the
  natural read is "someone pushed a red build".** Found 2026-08-15 by the CI-2
  agent, which nearly reported the branch tip as lint-red in frontend territory
  before catching itself. Before `pnpm install --frozen-lockfile`, `just lint`
  failed on 6 unmodified `apps/web/src/**` files and `pnpm -r typecheck` failed
  with `Cannot find module 'openapi-fetch'`. The proof it was the environment and
  not the tree: it extracted `apps/web/src/api/drawings.ts` from the committed
  blob at the tip, prettier failed those exact bytes, and the identical bytes
  passed after the install. Rule: **a new worktree is not ready until
  `pnpm install --frozen-lockfile` has run in it**, and a lint failure in a file
  outside your diff is a claim about YOUR environment until you have proved
  otherwise on committed bytes. Do not report it as a colleague's regression —
  that costs two agents' time and starts a hunt for a defect that does not exist.
- **A WORKTREE IS NOT NECESSARILY SEEDED FROM THE BRANCH TIP — check `git log -1`
  before you trust anything you read in it.** Found 2026-08-25 by the PICK-1
  agent, which was handed a worktree checked out at `3b0b29e` — a merge into
  `main`, **76 commits behind** `claude/branch-review-development-hkbbnb`. It
  noticed only because the spec its brief named (`apps/web/e2e/pick-anchor.spec.ts`)
  did not exist at all, reset to the remote tip, and went on to finish the job.
  **That detection was luck, and the luck does not generalise**: a MISSING file is
  loud, but a file that merely predates the branch by 76 commits reads as
  perfectly ordinary source, and an agent would then diagnose a bug that was
  fixed weeks ago, or build against an API that has since changed, and its
  eventual rebase would look like an unrelated conflict. Two rules: (a) the first
  action in any worktree is `git rev-list --count HEAD..origin/<branch>` — nonzero
  means reset before reading anything; (b) auditing this after a batch is cheap
  and worth doing, since the same command over every live worktree costs one
  shell call. Note the ordinary case is fine — the other four worktrees live at
  the same moment were 1–3 commits behind, i.e. just normally trailing — so this
  is an occasional seeding fault, not a standing condition, which is exactly what
  makes it easy to stop checking for.
- **PARAMS MODELS ARE PYDANTIC-DEFAULT `extra="ignore"`, so a payload that
  MISSPELLS a field validates, evaluates, and silently gives the OLD reading —
  and every gate agrees with it.** Found 2026-08-26 by the PATTERN-1 agent, in
  its own first draft: spelling the new selection `params.features` instead of
  `params.scope` returned 2xx, evaluated happily, and produced the legacy
  whole-body behaviour, with **seven tests passing against the wrong scope**.
  There is no server-side guard and there cannot easily be one — `extra="ignore"`
  is what makes the DTOs forward-compatible. Two consequences. (a) A contract
  test for a new param MUST assert on the RESULT (the geometry, the row, the
  bytes), never on the status code; a 2xx proves the request parsed, not that it
  meant anything. (b) When you add a field to a params model, the UI-side test
  that exercises it is the only thing standing between a typo and a silently
  ignored feature — write it in the same commit as the DTO, not with the UI.
  This is the `gen-check`-measuring-the-wrong-input trap in a third costume: the
  pipeline was healthy, the input was wrong, and everything downstream
  self-consistently confirmed it.
- OCP/OCCT wheels are large; in CI cache the uv environment keyed on the
  lockfile.
- **To test swapping an auditwheel-vendored library WITHOUT touching the shared
  `.venv`, check for `RUNPATH` (not `RPATH`) with `readelf -d`.** `LD_LIBRARY_PATH`
  takes precedence over `RUNPATH` but is beaten by `RPATH`, so when the consumer
  uses `RUNPATH` you can drop a replacement in a scratch dir, point
  `LD_LIBRARY_PATH` at it, and the real library is never mapped — prove which one
  loaded by grepping `/proc/self/maps` after the import. That is how the P0
  licence fix (a GPL-free `libjbig` stub) was validated against the full 2385-test
  geometry suite on 2026-07-31 with zero risk to a concurrent agent's environment.
  Mutating the shared `.venv` to test a swap would have broken every sibling.
- In this container, `uv python install 3.12` fails (403: the egress proxy
  blocks github.com release downloads of python-build-standalone — a policy
  denial, don't retry/route around). Not needed: system interpreters exist at
  `/usr/bin/python3.10`–`3.13`; with `.python-version` = 3.12, `uv sync`
  picks up `/usr/bin/python3.12` automatically. PyPI + npm registries are
  direct (proxy no-proxy list), so `uv sync` / `pnpm install` just work.
- `just` is not preinstalled: `uv tool install rust-just` → `~/.local/bin/just`.
- **This container has NO IPv6 loopback, so `localhost` here can only ever mean
  `127.0.0.1` — and every CI runner is dual-stack.** Anything that BINDS or
  PROBES a loopback address is therefore untestable locally in a way that *looks*
  tested: it passes here for the wrong reason. Cost a full round trip on
  2026-08-01, when the new e2e workflow's first three runs were ALL red —
  including the two that should have been green, which made the negative control
  worthless because it died in setup like the others. Cause: Vite forces
  `dns.setDefaultResultOrder("verbatim")`, so its default `localhost` host bound
  `::1` while `baseURL`/`webServer.url` asked for `127.0.0.1`; the process stayed
  alive and never answered. **The tell is the wording** — Playwright says
  "Timed out waiting Nms from config.webServer" for a live-but-silent server and
  "exited early" for a crash, and they are different bugs. Two rules: bind the
  LITERAL address (`--host 127.0.0.1`) rather than trusting name resolution, and
  **when a diagnosis cannot be reproduced locally, ship the PROBE with the fix** —
  `scripts/e2e.sh`'s CI preflight prints `127.0.0.1 -> 200, [::1] -> 000`, so a
  wrong diagnosis costs one log line instead of another round trip. Note the
  first instinct here (raise the 60 s timeout) was ruled out by measurement: with
  `apps/web/node_modules/.vite` deleted, Vite served in 1.3 s. A timeout is
  headroom, never a fix.
- **"github.com is blocked" is TOO COARSE: release-asset downloads are 403, but
  `git clone` over HTTPS WORKS — and so do `archive.ubuntu.com` and
  `files.pythonhosted.org`.** Measured 2026-08-01 while mirroring
  corresponding source (LIC-2): `curl -L
  https://github.com/Open-Cascade-SAS/OCCT/archive/refs/tags/V7_9_3.tar.gz` →
  **403**, same policy-denial class as the python-build-standalone block, while
  `git clone --depth 1 --branch V7_9_3 https://github.com/...` → **succeeds**
  (36 119 files). The brief for that task reasonably assumed the whole host was
  denied and pre-authorised a documented-only outcome; taking that at face value
  would have shipped an unverified recipe when the work could be — and was —
  fully executed and checksummed here. Rule: when you need bytes from a denied
  host, check whether a DIFFERENT protocol or a different upstream serves the
  same artefact before concluding it is unfetchable. Corollary in the same
  session: the legacy PyPI path
  `files.pythonhosted.org/packages/source/<l>/<name>/<file>` returned a
  **zero-byte body with a SUCCESS status**, while the hashed
  `/packages/<a>/<b>/<sha>/<file>` URL from the JSON index returned the real
  file. A zero-byte 200 is the worst failure shape there is — every digest check
  downstream agrees with itself — so assert on size, and prefer the URL the
  index gives you over a path you constructed.
  **Measured egress map, extended 2026-08-01 (LIC-4).** REACHABLE: `git clone`
  over HTTPS, `raw.githubusercontent.com`, `archive.ubuntu.com`,
  `files.pythonhosted.org`, `conda.anaconda.org`. DENIED (`CONNECT 403`): every
  distro source host probed — nine of them, incl. the CentOS/AlmaLinux vaults —
  and github.com *release assets*. The practical consequence is that
  distro-built binaries cannot have their SRPMs mirrored from here, so a task
  needing corresponding source for one of them must either derive the answer
  from artefacts already on disk or write down why it does not need the source
  at all. Full table with the probe list: `docs/LICENSING.md` §7.5.
- **The blocked registry means NOTHING about the image build is locally
  testable, so anything the build depends on needs a gate that does not build.**
  `.dockerignore` excludes `scripts`, `deploy` and `docs` wholesale and then
  re-includes named files with `!` negations; a `COPY` whose source is not
  negated resolves to NOTHING and fails the build. That failure is unreachable
  here by construction — no `just` target can produce it — so its first and only
  signal is the `deploy-path` workflow, the slowest one we run. It cost two red
  commits on 2026-08-01: LIC-2 added `scripts/corresponding_source.py` to the
  runtime COPY (check-licences.py imports it) with no negation, and all three
  service images failed while `ci` and `e2e` stayed green, because neither
  builds an image. Second time the list had lost an entry, which is the tell
  that the *allow-list* is the defect. Fix: `scripts/check-build-context.py`
  re-implements moby's `MatchesOrParentMatches` and asserts every Dockerfile
  COPY source exists and survives `.dockerignore` — stdlib, no daemon, ~10 ms,
  wired into `just lint` and CI's `compose` job. Two things generalise. (a) When
  a whole class of failure is unreachable locally, re-implement just enough of
  the absent tool to gate it, and CROSS-CHECK the re-implementation against a
  real one rather than trusting it (this matcher was diffed against the docker
  SDK's own context walk over all 445 included entries — zero disagreements; a
  naive comparison against the SDK's `matches()` shows 190 false differences,
  because that method is the depth-limited variant and directory pruning happens
  in `walk()`). (b) Ship the gate with a `--self-test` that reproduces the
  defect and demands a failure, exactly as `just licence-selftest` does.
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
    **Always `rm -f` the SQLite files first — `create_all` does NOT migrate.**
    `metadata.create_all` is a no-op on a table that already exists, so a
    scratchpad `documents.db` left by an earlier session is silently reused at
    ITS old schema. Seen 2026-07-25: a db from 07-23 made every e2e spec fail
    at `new-sketch` with gateway 500s — `no such column: features.suppressed`,
    a column added after that file was written. The failure looks like a code
    regression and is not one, and it gets worse the longer a container lives
    (the schema drifts further each day). Start every native boot from fresh
    files.
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
- **A long-running native uvicorn on a scratchpad SQLite file starts returning
  `attempt to write a readonly database` after ~10 minutes, and it reads exactly
  like a code regression.** Symptom: register -> 500, every spec dies at
  `seedSession`, while a FRESH process writes the same file fine. Nothing in the
  app changed; the long-lived connection's handle goes bad. Restarting the three
  services clears it, so bounce them before each e2e leg rather than debugging the
  500 — an agent lost time to this on 2026-07-30 chasing a phantom regression.
  **AND THE SAME 500 HAS A SECOND CAUSE UNDER PARALLELISM: a sibling deleted your
  database. PREFIX SCRATCHPAD DB FILENAMES PER AGENT.** The session scratchpad is
  SHARED, so `$SP/documents.db` / `$SP/gateway.db` are the obvious names for
  everyone — and the boot recipe says to `rm -f` them first, because `create_all`
  does not migrate. So agent B's perfectly correct "start from fresh files" step
  unlinks the file agent A's live uvicorns are holding open, and A's gateway
  returns `attempt to write a readonly database` from then on (deleted inode,
  still-open handle). Measured 2026-08-02 with four agents live: isolating the
  PORTS is not enough, the DATABASE PATH has to be isolated too. Use
  `$SP/<slug>-documents.db` / `$SP/<slug>-gateway.db` and `rm -f` ONLY your own
  prefix — never an unprefixed file, which may be someone's live stack. Note the
  symptom is identical to the stale-handle case above and to the stale-Vite case,
  so before diagnosing a 500 at register, restart YOUR stack on YOUR own files and
  re-run; three separate environment faults wear the same mask.
- **A `conftest.py` env var leaks ACROSS services, because pytest collects every
  conftest before running any test.** `services/gateway/tests/conftest.py` does
  `os.environ.setdefault("LOFT_ENV", "dev")` so the gateway suite can build
  settings; in a whole-repo `uv run pytest` that dev posture is therefore already
  in `os.environ` when the documents and geometry suites run. The failure mode is
  the nasty direction: a test asserting a NON-dev behaviour (e.g. that the
  datastore-credential guard refuses to boot) passes when its file is run alone
  and fails in the full sweep — or worse, a test asserting the dev-allow path
  passes in the sweep for the wrong reason. Any test whose subject depends on
  `LOFT_ENV` (or any other conftest-seeded variable) must `monkeypatch.delenv`
  / `monkeypatch.setenv` EXPLICITLY rather than inherit, and should assert the
  non-dev case by name. Found 2026-07-30 while landing the fail-closed guard.
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
- **`pnpm run <script> -- <args>` DROPS the `--` in pnpm 10, so the args never
  reach the script — and this is the GENERATOR of the stale-Vite trap below.**
  Measured on pnpm 10.33.0: `pnpm --filter @loft/web dev -- --port 5199` starts
  Vite on **5173** with no error, while `dev --port 5199` and `exec vite --port
  5199` both bind correctly. The `--` separator is npm-idiomatic, so the failure
  is produced by CORRECT muscle memory and reported by nothing. The invocation an
  agent reaches for to boot an ISOLATED frontend is therefore the one that
  silently takes the SHARED port; `reuseExistingServer: true` then hands that
  stray 5173 to the next `just e2e`, whose specs all 500 at `seedSession` against
  a torn-down gateway and read as a code regression. Never write `--`; always
  confirm the port Vite actually printed. Half of this is now closed in code:
  `apps/web/vite.config.ts` sets `server.strictPort`, so a Vite that cannot take
  the port it was given FAILS instead of falling back to 5173. The swallowed
  argument is still silent — that part only discipline fixes.
- **`apps/web/test-results/` LOOKS like the ideal scratch directory and Playwright
  WIPES IT at the start of every run — including your live SQLite files.** It is
  gitignored AND prettier-ignored AND inside the linted tree, which is exactly the
  combination an agent needing a throwaway config hunts for, so this is a trap
  correct reasoning walks into. Cost a restart on 2026-08-15: an isolated
  Playwright config and two SQLite DBs were placed there, the first run deleted
  them mid-flight, and the unlinked-inode DBs produced precisely the
  `attempt to write a readonly database` / "500 at create-part" mask the recipes
  above describe — i.e. it wears the same costume as three other faults. Two more
  traps in the same corner, both measured: **Node refuses to type-strip a `.ts`
  Playwright config located under `node_modules/`**, so an isolated config there
  must be `.mjs`; and **`apps/web/playwright.config.ts` hardcodes
  `baseURL: 5173` with no env override**, so running against an isolated Vite port
  needs a whole separate config file, not a flag. The working recipe, which
  survives all three: `apps/web/node_modules/.vp1a/<name>.config.mjs` — gitignored
  via `node_modules`, eslint-ignored via `**/node_modules/**`, and not wiped.
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
- **A TAILWIND PRESET CHANGE IS A BUILD-CONFIG CHANGE, NOT A SOURCE CHANGE — a
  running Vite will not pick it up, and the symptom is "your new feature is
  broken", never a build error.** Measured 2026-08-17 recovering VIEWCUBE-1.
  `packages/design/src/tailwind-preset.ts` gained `h-view-cube` /
  `bottom-view-cube` utilities in the same change that used them. Against a Vite
  started BEFORE the patch, those classes did not exist, so the host `div` had
  no width, height or seat — and its child `<canvas>` fell back to the HTML
  DEFAULT of **300x150 at the top-left**. The e2e probe therefore reported a
  cube of the wrong size in the wrong corner, which reads exactly like a
  half-finished component. I was one step from rewriting work that was already
  correct; after killing Vite the same bytes measured **108x108 at (1130, 602)**
  on a 1280x800 frame with every facet click steering the camera.
  Two things generalise. (a) **`300x150` is a fingerprint, not a measurement** —
  it is the intrinsic size of a `<canvas>` with no CSS size, so any element
  reporting it is un-styled rather than mis-styled, and the question is why the
  CSS is missing, not what the component did wrong. (b) The stale-Vite entry
  above is about a stale PROXY TARGET (every spec 500s at register, loud and
  obvious). This is the quieter half: a stale *config* yields a page that loads,
  renders and lies. **Restart Vite after touching `tailwind-preset.ts`,
  `tokens.ts`, `vite.config.ts`, or anything else Vite reads once at boot** —
  the same reflex as regenerating contracts after a pydantic change.
- **Run the batch-end `just e2e` in a QUIET window — never concurrent with
  heavy agents — and treat a red sweep run under CPU load as UNCONFIRMED.**
  Seen 2026-07-23: a batch-end sweep kicked off while 2-3 kernel agents were
  running geometry pytest + booting isolated stacks came back 2 failed / 188
  passed; both failures were 5s-timeout UI-state waits in the heaviest specs
  (`full-flow.spec.ts` register→sketch→extrude→export, `sketch-on-face.spec.ts`)
  — `new-extrude` "solve a sketch first" still disabled, `sketch-strip`
  toHaveCount(0) got 1. The discriminator that proves FLAKE not regression: the
  failure POINT MOVED between runs (extrude-enable one run, sketch-strip-dismiss
  the next) — a real code regression fails identically every time; a
  contention flake wanders to whichever 5s-gated step loses the CPU race that
  run. The diff under test (`beb3a21`, drawings-only) didn't touch the
  sketch/extrude path, and 188 specs passed. Procedure: (a) don't overlap the
  gate with agent load; (b) if it happens, reconfirm the specific failures by
  an isolated rerun in a QUIET window before concluding regression — but a
  moving failure point is already a flake tell; (c) the heavy founder-flow
  specs' intermediate waits use the default 5s (the `eval-status` wait already
  uses 30s) — bump the solve/UI-state-gated ones to a generous timeout so the
  gate is contention-robust (filed as a spec-hardening item, same class as the
  raster tolerance fix).
- **A bisect that reproduces a failure at an "earlier green" commit proves the
  failure is NOT in the diff under test — but it does NOT prove "environment."
  Confirm the actual assertion before naming a cause.** Cautionary tale
  (2026-07-22): a batch-end `just e2e` failed 6 specs; a four-point bisect (HEAD
  → `0c10265` → `47c88f4` → `24b1c53`) reproduced them all at a commit believed
  green, and the orchestrator concluded "container-restart raster drift" and
  filed it as such. A qa-tester then read the specs and found the real cause: 5
  of the 6 (the measure specs) asserted the STALE pre-units-convention readout
  string `"37.42"`, but the units change (`70ce39d`, 2026-07-17) switched the
  readout to `formatLength` → `"37.4166 mm"` — and that commit is an ANCESTOR of
  all three bisect points, so they were deterministically red there too, for a
  code/assertion reason, not the environment. The `toHaveText("37.42")` timeout
  was misread as "the readout never appears" when it appears with the correct
  value in a new format. Only the undo-redo 1280 band-fit (`≤0px` → `Received:
  1`) was genuine sub-pixel raster drift (fixed with a documented ≤2px
  tolerance). Lessons: (a) the "green" end of a bisect must be a commit you have
  actually seen pass, not one assumed to; a shared ancestor bug hides from every
  bisect point below it. (b) Before concluding "environment," open the spec and
  read the EXACT expected-vs-received — a stale golden/format string and a raster
  miss look identical through a `toHaveText` timeout. (c) DOM-overlay picks
  (`getByTestId("measure-vertex-N")`) are already raster-independent, so "pick
  coords drifted" was never even applicable to those specs. Measure/undo-redo
  specs are container-robust as of `1e1395d`.
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
- **`just gen` reads the WORKING TREE, so in a shared tree it silently bakes
  another agent's uncommitted schema into YOUR commit — and `gen-check` cannot
  see it, by construction.** `scripts/gen-contracts.py` imports the live source,
  so the generator's input is whatever is on disk. `gen-check` then regenerates
  *the same way* and diffs against the committed JSON, i.e. it asks "do the
  committed contracts match the working tree?" when the standing rule needs "do
  they match the committed SOURCE?" Those coincide for a single developer and
  come apart exactly when several agents are editing schemas at once. Seen
  2026-07-31: an agent's `just gen` captured a sibling's uncommitted gateway
  duplicate-route work, so its commit carried `gateway.openapi.json` +
  `gateway/schema.ts` describing routes with no committed source — gen-check-RED
  in CI on that commit, while passing locally. It was caught by hand and
  force-pushed over. The tempdir in `gen-check.sh` protects the tree from being
  DIRTIED; it never made the INPUT clean, which is the property that matters.
  **Fix, shipped the same day: `just gen-verify` (`scripts/gen-check.sh
  --from-index`)** materialises the git INDEX — the tree `git commit` would
  write — into a throwaway worktree and generates there, so it answers "will CI
  be green on my commit". Verified against the real defect rather than asserted:
  with a schema change present only in the working tree and only the generated
  output staged, the default mode exits **0** (blessing a commit CI rejects) and
  `--from-index` exits **1** naming the leaked field. Run `just gen-verify`, not
  `just gen-check`, before committing anything that touches a pydantic model
  while other agents are live. CI itself is unaffected — it checks out a clean
  tree, so there index == HEAD == worktree and the default mode is already right.
  The general lesson is the one this repo keeps relearning: **a gate is only as
  honest as its INPUT, and "it passed" tells you nothing until you know what it
  measured.** **(2b) `prettier --check .` walks the FILESYSTEM,
  not the index, so an UNTRACKED scratch file fails lint for every agent at
  once** — and `.prettierignore` covers `docs/`, `.claude/`, generated dirs and
  build output, but NOT the repo root. Seen 2026-07-30: an agent left a
  180-byte `eval1.json` (an evaluate-response dump) at the root; it never would
  have been committed, and it would still have turned the batch-end `just lint`
  red for everyone, looking like someone else's regression. Payload dumps,
  curl output and one-off fixtures go in the session scratchpad, never the repo
  root. When you find one that is another agent's, tell that agent — do not
  delete it; it may be in active use. **(2c) Some temp files CANNOT go in the
  scratchpad — those must be `prettier --write`-clean before you walk away from
  them.** `apps/web/playwright.config.ts` sets `testDir: "./e2e"`, so a throwaway
  spec has to live inside `apps/web/e2e/` to be discovered at all; the scratchpad
  is not an option, and `.prettierignore` does not cover that directory. Seen
  2026-07-31: the orchestrator wrote a temporary founder-capture spec there,
  deleted it minutes later, and in the window between, a concurrent agent's
  `pnpm run lint` went red on formatting alone — a failure in nobody's diff, in a
  file that no longer exists by the time anyone looks. Rule: anything you must
  place inside a linted tree gets formatted the moment it is written, not when it
  is committed (it never will be), and gets deleted in the same turn.
  **(3) Lint with `uv run ruff …`, NEVER a
  bare PATH `ruff`.** Seen 2026-07-23 (interference slice `e46db16`): the agent ran a PATH
  `ruff check` that predated the `RUF002` confusable rule and reported "0 errors,"
  but the locked `uv run ruff check` (0.15.20) flagged 8× `RUF002` (a test file
  using U+00D7 `×`/U+2212 `−` glyphs — every other file uses ASCII `x`/`-`) + 1×
  `SIM300`, so HEAD shipped lint-red under a false "lint clean" claim (geometry-QA
  caught it). A bare `ruff` resolves to whatever's on PATH, which can be older than
  the lockfile; `uv run ruff` always uses the pinned 0.15.20 CI installs. Prefer
  ASCII in code/tests (`x`, `-`, `<=`) — reserve `×`/`−`/`≤` for docs/markdown.
- **When a concurrent agent's unfinished work blocks a clean full `just lint`,
  scope your gate to your ENTIRE diff — every file you touched — not just the
  primary source file.** Cautionary tale (2026-07-23, overnight loop): a
  first-angle-projection slice (`822b3a9`) changed `bounds_aware_layout`'s
  signature in `compose.py` AND the call sites in `test_drawings_compose.py`,
  but — unable to run repo-wide `just lint` because a concurrent frontend agent
  had unfinished `apps/web` work — ran only scoped `pyright compose.py`. That
  passed; the signature change left 7 `pyright` errors in the TEST file
  (`dict[str, ViewBounds]` vs the new `dict[ViewProjection, ViewBounds | None]`),
  so HEAD shipped lint-red and a sibling agent caught it. A scoped gate is fine
  when the tree is dirty with foreign work, but scope it to `git diff --name-only`
  (your whole change), e.g. `uv run pyright <each changed .py>` + `ruff` on all
  of them — never just the one file you were "mainly" editing. A signature change
  breaks its callers and tests, which single-file scoping can't see.
