# Autonomous Build Loop — Blueprint

What this project needs to keep itself looping and building, compiled from a
review of [Overcastly-AI/Next-Lane](https://github.com/Overcastly-AI/Next-Lane)
(commit `ea8c262`), a tracker whose 300+ commits were all authored by an
autonomous Claude Code agent team. This document adapts that system to an
open-source, Python-backed 3D CAD product.

---

## 1. How Next-Lane's loop works (the model we're copying)

The system has four layers. Remove any one and the loop degrades.

### 1.1 The direction layer — docs as the org's shared memory

Everything the agents decide, learn, and queue lives in versioned markdown, so
any fresh agent session can rebuild full context from the repo alone:

| Doc | Role | Owner |
|---|---|---|
| `docs/VISION.md` | North star + the **operating question** every decision answers (theirs: "Is this better than Jira?"), plus an honest competitive scorecard (better / parity / behind) | `vision-steward` agent |
| `docs/ROADMAP.md` | Phases with ✅/🚧/⬜ status markers; **source of truth for "what phase are we in"** | build agents + groomer |
| `docs/BACKLOG.md` | Single prioritized dev board with a **"Ready" queue of 5–10 well-formed items** the build loop pulls from | `backlog-groomer` agent |
| `docs/AUDIT-PRODUCT.md` / `docs/AUDIT-ENGINEERING.md` | Two **independent** deep audits (deliberately don't coordinate) that feed the groomer | auditor agents |
| `docs/UI-REVIEW.md` | UX/consistency findings from a read-only QA agent | `frontend-qa` agent |
| `docs/RETRO.md` | Honest retros on the loop itself; the spec for fixing it | orchestrator |

The **non-negotiable doc-sync rule:** every commit that lands a feature must
update ROADMAP + BACKLOG status *in the same commit*. Stale docs are treated as
defects, and every groom pass reconciles the docs against `git log`.

### 1.2 The agent team (`.claude/agents/`)

Specialists, not one generalist. Three groups:

- **Builders** (write code): `schema-architect` (data model), `backend-builder`,
  `frontend-builder`.
- **Quality** (independent from whoever wrote the code): `code-reviewer`,
  `qa-tester` (real-browser Playwright, desktop AND mobile), `frontend-qa`
  (design/a11y audit, read-only on app code), `mcp-consumer-qa` (exercises the
  product through its own agent API).
- **Direction** (read-only on app code, they steer): `product-auditor`,
  `engineering-auditor`, `backlog-groomer`, `vision-steward`, plus
  `doc-syncer` (cheap-model doc reconciler run each iteration) and
  `oss-curator` (owns README/community surface, "truth-only" — every badge and
  claim verified).

### 1.3 The workflows (`.claude/workflows/`)

Orchestration recipes run with the Claude Code `Workflow` tool:

1. **`build-vertical-slice`** — one feature: plan → schema → backend →
   frontend → review → verify, each phase a specialist agent.
2. **`nightly-build-loop`** — pick next ⬜ roadmap item → run
   build-vertical-slice → commit + tick roadmap → repeat until done or budget
   is low. Guardrails: never push red; a slice failing twice stops the loop
   with a note instead of looping forever.
3. **`autonomous-dev-loop`** — the full org loop: parallel independent audits →
   groom the Ready queue → build the top N items in parallel (each in an
   isolated git worktree + per-instance DB/ports) → integrate green branches →
   **immediately launch the next batch** (completion-driven, not timed).

### 1.4 The survival layer (from their RETRO — SPECIFIED THERE, NOT IMPLEMENTED)

> **PROVENANCE CORRECTION, 2026-08-14.** This section originally read "this is
> the part that actually keeps it looping", which overstated it. A grep of
> Next-Lane's repository finds the watchdog **only** in their `docs/RETRO.md`,
> as an unchecked `- [ ]` action item; their live workflow doc says
> "re-invoke on completion / `ScheduleWakeup`" with no watchdog at all. Their
> own agent confirms it independently: the scheduled self-check-in "needed a
> permission approval that errored out."
>
> So this is a **specification they wrote and did not build**, imported here as
> though it were a working mechanism. The reasoning below is still sound and our
> own history confirms it — but do not go looking for their implementation, and
> do not treat "Next Lane does this" as evidence that it works. What actually
> wakes a loop, measured, is in `docs/LOOP-MECHANISMS.md`.

Their loop initially stalled overnight and needed human restarts. Root causes
and the fixes, verbatim from `docs/RETRO.md`:

1. **Watchdog cron (~every 20 min), idempotent.** Completion-driven dispatch is
   the pacer, but a recurring stall-recovery job is the safety net: if agents
   are running → no-op; if the tree is dirty → commit/clean per policy; else →
   dispatch the next Ready item. "Event-driven *without* a heartbeat has no
   recovery path."
2. **Never barrier shipping on planning.** Builds always pull from the
   *existing* Ready queue; audits/grooming refresh the board asynchronously. A
   dead auditor must never stall builds (theirs did — twice).
3. **Retry-once-then-skip.** Transient agent failures get one retry, then the
   loop skips to the next item and logs it. No single flaky step blocks the
   pipeline.
4. **Write-early.** Auditors append findings incrementally so a late crash
   doesn't lose work.
5. **Always arm the next iteration.** Every iteration ends by dispatching the
   next batch or arming the watchdog — the loop can never reach a state with
   nothing scheduled.
6. **Liveness checks on wakeup.** The orchestrator checks in-flight agents'
   output mtimes; >30 min stale without a known long gate = reap and relaunch
   (preserving, not reverting, the dead agent's uncommitted work).

**Their acceptance test for "autonomous":** zero human messages for 8 hours
while the loop keeps the build green, ships Ready items, refreshes the board,
and recovers from any single agent/tool failure. Human input is *steering*,
never *restarting*.

### 1.5 Standing guardrails (from their CLAUDE.md)

- **Never push a red build.** Commit only when full gates are green; one commit
  per item; revert/discard on failure.
- **Parallel by default** — isolated worktrees + per-instance environments;
  parallel agents get **disjoint file territories** in their briefs and stage
  only their own files (never `git add -A`).
- **QA exercises the real artifact**, not just unit tests — real user flows,
  the actual production build, cross-page state coherence. "Tests pass" ≠
  "works for the user."
- **No hand-waving** — never dismiss a failure as "pre-existing" without
  root-causing it.
- **Definition of done** = builds + typecheck + tests green + docs ticked +
  committed & pushed.
- **Founder updates are results-first** — what shipped with evidence
  (numbers, screenshots), then what's running, then what's next; sent
  proactively at milestones.

---

## 2. Adapting this to an open-source Python 3D CAD

Same skeleton, different specialists and different QA physics. What carries
over unchanged: the doc trio, the groomer/auditor/builder separation, the
workflows, the watchdog, and every guardrail above.

### 2.1 The operating question

Next-Lane's is "Is this better than Jira?". Ours needs an equivalent daily-driver
bar against the incumbents (SolidWorks / Fusion 360 / Onshape / FreeCAD), e.g.:

> **"Would a mechanical engineer choose this for a real part today?"**

with a VISION.md scorecard tracking better / parity / behind per dimension
(sketching, constraints, part modeling, assemblies, STEP interop, performance
on large models, drawings, ...). Structural advantages to exploit (the analog
of their four): free & unlimited, your data/your compute (no cloud-locked
files), open & extensible (Python API as a first-class feature), and
AI-native/agent-native (an MCP server so agents can drive the CAD kernel —
no incumbent has this).

### 2.2 Agent team, translated

| Next-Lane agent | 3D CAD equivalent | Notes |
|---|---|---|
| `schema-architect` | `kernel-architect` | Owns the geometry kernel layer (OCCT via OCP/build123d, sketch/constraint model, document format) |
| `backend-builder` | `backend-builder` | Python API/services (FastAPI or similar), geometry operations, file I/O (STEP/STL/IGES) |
| `frontend-builder` | `frontend-builder` | Viewport + UI (three.js/WebGL web client, or Qt) |
| `qa-tester` | `qa-tester` **plus geometry QA** | Real-app flows *and* geometric correctness: golden-model regression (volume/area/topology invariants), STEP round-trip fidelity, constraint-solver determinism, performance budgets on reference models |
| `frontend-qa` | `frontend-qa` | Viewport rendering/visual regression joins the a11y/consistency audit |
| `mcp-consumer-qa` | `mcp-consumer-qa` | Exercises the CAD through its own MCP/scripting API — parametric modeling as an agent surface |
| auditors / groomer / vision-steward / doc-syncer / oss-curator | unchanged | Direction layer is domain-agnostic |

### 2.3 CAD-specific definition of done

A CAD feature isn't done when tests pass; it's done when:
- geometry gates are green (golden-model suite + kernel round-trip tests),
- the flow works in the real running app (open → model → export),
- performance budget holds on reference parts,
- the Python scripting/MCP surface exposes the feature (or an explicit
  "not agent-appropriate" note),
- ROADMAP/BACKLOG ticked in the same commit.

### 2.4 CI gates (their `.github/workflows/` pattern)

- `ci.yml` — lint (ruff), typecheck (mypy/pyright), unit tests, build.
- `e2e.yml` — full-app end-to-end (browser or UI harness) + geometry
  regression suite.
- `docs.yml` — docs site build/deploy.
- `images.yml` — Docker images so `docker compose up` stays the 60-second start.

---

## 3. Bootstrap checklist for this repo

Phase 0, in order:

- [ ] `docs/VISION.md` — thesis, operating question, incumbent scorecard
- [ ] `docs/RESEARCH.md` — kernel decision (OCCT/OCP vs. alternatives), frontend
      decision (web/three.js vs. Qt), architecture, licensing
- [ ] `docs/ROADMAP.md` — phased plan with ✅/🚧/⬜ markers (Phase 1 = thinnest
      vertical slice: sketch → extrude → view → export STEP)
- [ ] `docs/BACKLOG.md` — dev board with a Ready queue
- [ ] `CLAUDE.md` — constitution: operating principles, stack, conventions,
      doc-sync rule, multi-agent protocol, environment recipes
- [ ] `.claude/agents/` — the team above
- [ ] `.claude/skills/` — vendor Superpowers (obra/superpowers, MIT) as
      Next-Lane did, + project skills (`run-stack`, `geometry-qa`, ...)
- [ ] `.claude/workflows/` — `build-vertical-slice`, `nightly-build-loop`,
      `autonomous-dev-loop` adapted to the Python stack
- [ ] CI workflows + Docker Compose scaffold
- [ ] Watchdog: recurring stall-recovery trigger per §1.4 (idempotent no-op
      when healthy)
- [ ] Community surface: README, LICENSE (MIT), CONTRIBUTING, SECURITY,
      issue templates
