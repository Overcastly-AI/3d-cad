# Workflow: autonomous-dev-loop

The full Loft "org" loop. Two independent auditors set direction, the groomer
maintains the board, and the build loop ships the top items — each reviewed
and QA'd. Loops **on completion** (next batch starts when this one ends), with
a **watchdog** as the stall-recovery fallback (`docs/AUTONOMOUS-LOOP.md` §1.4).

## Cadence — completion-driven, watchdog-backed

Each invocation runs one batch. On completion the orchestrator immediately
launches the next batch. Independently, a recurring stall-recovery routine
(~20–30 min) checks: agents active → no-op; dirty tree → reconcile per
protocol; idle + Ready non-empty → dispatch the next item. The watchdog is
recovery, not the pacer. Stop only when Ready is empty AND the auditors
propose nothing new, or the founder says stop.

## The stall lessons (inherited from Next-Lane's retro — do not relearn them)

1. **Never barrier building on planning.** Builds pull from the *existing*
   Ready queue; audits/groom refresh the board as a side-channel. A dead
   auditor must never stall shipping.
2. **Retry once, then skip** any flaky agent step; log and continue.
3. **Auditors write early** (append incrementally) so crashes lose nothing.
4. **Every batch ends by arming the next** (dispatch or watchdog re-arm) —
   the loop may never reach a state with nothing scheduled.
5. **Liveness:** on every orchestrator wakeup, check in-flight agents' output
   mtimes; >30 min stale without a known long gate → investigate, reap,
   relaunch. Preserve (never revert) a dead agent's uncommitted work.

## Phases per batch

1. **Build (starts immediately)** — pull top N (2–4) **disjoint** Ready
   items; run each as a `build-vertical-slice` in its own git worktree with
   per-instance compose ports (`scripts/dev-instance.sh N`). Green → integrate
   to the working branch + tick board; red after retry → discard worktree,
   park item with a note.
2. **Audit (parallel side-channel, every other batch or on idle)** —
   `product-auditor` and `engineering-auditor` run independently, appending
   to their docs. Never blocks phase 1.
3. **Groom** — `backlog-groomer` reconciles ROADMAP vs git log, ingests
   audits + `docs/UI-REVIEW.md` + `docs/GEOMETRY-QA.md`, refreshes Ready.
4. **Sync & report** — `doc-syncer` pass; results-first founder update at
   milestones (shipped + evidence, running, next).

## Guardrails

- Never push red. One commit per item. Parallel items in isolated worktrees;
  integrate only when green.
- Bounded batch (N≈2–4) so each run stays reviewable.
- Read-only roles (auditors, QA, steward) never touch app code.
- Geometry gates are mandatory for kernel-adjacent items — no exceptions for
  "it's just a small feature."

## Script outline

```js
export const meta = { name:'autonomous-dev-loop',
  description:'Build Ready items in parallel worktrees; audits+groom as side-channel; loop on completion',
  phases:[{title:'Build'},{title:'Audit'},{title:'Groom'},{title:'Sync'}] }
phase('Build')
const ready = /* top N disjoint Ready items from docs/BACKLOG.md */ []
const built = await parallel(ready.map(item => () =>
  workflow('build-vertical-slice', { item }).catch(() => null)  // retry/park handled inside
))
phase('Audit')  // side-channel: failures here never block the next batch
await parallel([
  () => agent('Deep product audit; append docs/AUDIT-PRODUCT.md.', {agentType:'product-auditor'}).catch(() => null),
  () => agent('Deep engineering audit; append docs/AUDIT-ENGINEERING.md.', {agentType:'engineering-auditor'}).catch(() => null),
])
phase('Groom')
await agent('Reconcile ROADMAP vs git log; refresh the Ready queue.', {agentType:'backlog-groomer'})
phase('Sync')
await agent('Doc-sync pass.', {agentType:'doc-syncer'})
// orchestrator: integrate green branches, report at milestones, launch next batch, keep watchdog armed
```
