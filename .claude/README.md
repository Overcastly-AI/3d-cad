# Claude Code tooling for Loft

The agent org that builds this project: **agents** (the team), **skills**
(how-to playbooks), **workflows** (orchestration recipes). Modeled on the
system that built Next-Lane (see `docs/AUTONOMOUS-LOOP.md`), tailored to a
Python-microservices CAD platform.

## Agents (`agents/`)

| Agent | Role |
|-------|------|
| `kernel-architect` | Geometry service: OCCT/OCP/build123d, features, tessellation, export, sketch solver. Only agent allowed to touch kernel code |
| `backend-builder` | Gateway + documents services, `py-kit`, contracts regeneration |
| `frontend-builder` | React SPA + react-three-fiber viewport |
| `platform-builder` | Compose/Docker/CI/justfile, contract pipeline, per-instance dev envs, Helm later |
| `code-reviewer` | Independent diff review: correctness, DRY, boundaries, licenses (read-only) |
| `qa-tester` | Independent functional QA on the real stack — Playwright, desktop + touch |
| `geometry-qa` | Golden models, STEP round-trips, determinism, perf budgets → `docs/GEOMETRY-QA.md` |
| `frontend-qa` | Design-system/a11y/responsive/viewport-UX audit → `docs/UI-REVIEW.md` (read-only) |
| `product-auditor` | Independent daily-driver audit → `docs/AUDIT-PRODUCT.md` (doesn't coordinate with engineering-auditor) |
| `engineering-auditor` | Independent code-health/security/license audit → `docs/AUDIT-ENGINEERING.md` |
| `backlog-groomer` | Reconciles ROADMAP vs git log; maintains `docs/BACKLOG.md` Ready queue |
| `vision-steward` | Founder ideas → VISION/ROADMAP/BACKLOG; owns the daily-driver scorecard |
| `doc-syncer` | Cheap-model doc reconciler (ARCHITECTURE/README/CHANGELOG), every iteration |
| `oss-curator` | README + community surface; truth-only claims |

## Skills (`skills/`)

| Skill | Trigger |
|-------|---------|
| `run-stack` | Bring the stack up (single, per-agent instance, or full compose artifact) and verify it |
| `geometry-gates` | Run/extend golden models, round-trips, determinism, budgets — mandatory for kernel-adjacent work |
| `add-microservice` | Add a new service the DRY way (and challenge whether you should) |
| `frontend-design` | **Mandatory for ANY UI work** (CLAUDE.md design mandate) — distinctive, intentional visual design; vendored Anthropic skill (Apache-2.0, see its `LICENSE.txt`) |

Recommended additions from the Superpowers plugin (`/plugin marketplace add
obra/superpowers`): TDD, systematic-debugging, writing-plans,
verification-before-completion, using-git-worktrees. Next-Lane vendored these;
we use the plugin (network policy permitting) or vendor them later.

## Workflows (`workflows/`)

| Workflow | Purpose |
|----------|---------|
| `build-vertical-slice` | One backlog item: plan → kernel → backend → frontend → review → QA |
| `nightly-build-loop` | Work down the Ready queue unattended; retry-once-then-park |
| `autonomous-dev-loop` | The org loop: build batch in parallel worktrees + audits/groom side-channel; loops on completion, watchdog-backed |

The loop's survival rules (watchdog, never barrier builds on planning,
retry-then-skip, write-early, always arm the next iteration) are documented
in `docs/AUTONOMOUS-LOOP.md` §1.4 — inherited from Next-Lane's retro so we
don't relearn them the hard way.
