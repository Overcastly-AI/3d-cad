# Workflow: nightly-build-loop

Work down the Ready queue unattended, batch after batch, until the queue is
empty or the token budget runs out. Designed for long runs with no human in the
loop.

## How it operates

1. Run one batch of `autonomous-dev-loop` (audit → groom → build N in worktrees).
2. Integrate the green branches; verify the **merged** tree before pushing.
3. Read CI for the pushed commit.
4. **Immediately start the next batch** — chained on completion, inside this
   same run. Not scheduled, not polled.
5. Stop when the Ready queue is empty, a slice has failed twice, or
   `budget.remaining()` is too low to start another batch safely.

## There is no cron, and that is deliberate

Removed 2026-08-14 by founder directive. We had made a 15-minute cron the
**pacer** against slices that took three and a half hours: it woke roughly
fourteen times per slice, and each wake did more orchestrator hand-work —
filing board items, re-triaging, re-reading CI. That is what "racing before the
next cron job kicks off" meant, and it was self-inflicted.

Next-Lane's retro is explicit that a watchdog is *stall recovery*, never the
pacer: "it only acts when the loop is idle; when work is in flight it no-ops and
re-arms." We had it backwards. Chaining on completion removes the need for the
timer entirely — the loop cannot go idle if every batch launches the next one.

If a stall-recovery net is ever reinstated, it must be a genuine no-op when
agents are live: check in-flight agents' output mtimes first and return without
doing anything if any are fresh.

## Guardrails

- Each batch must leave the repo **building and committed** — never push red.
- A slice that fails twice stops the loop with a note rather than looping.
- Bounded batch size (N≈2–4) so each run stays reviewable.
- Prefer thin working slices to broad broken ones.
- **The orchestrator does not audit, groom, or write the board.** Those are the
  auditors' and the groomer's jobs, and doing them by hand is what made the
  previous loop expensive and collision-prone. See
  `.claude/workflows/autonomous-dev-loop.md` for the audit that found eight of
  fourteen agents had never been invoked.

## Script outline

```js
export const meta = { name:'nightly-build-loop',
  description:'Chain autonomous-dev-loop batches until the queue or the budget runs out',
  phases:[{title:'Batch'}] }

let dry = 0, batch = 0
while (dry < 2 && (!budget.total || budget.remaining() > 250_000)) {
  phase('Batch')
  const r = await workflow('loft-dev-loop', { batchSize: 3, skipAudit: batch % 3 !== 0 })
  batch += 1
  if (!r || r.greenBranches.length === 0) { dry += 1; continue }
  dry = 0
  // orchestrator integrates + verifies + pushes between batches
}
```

`skipAudit` on most batches is intentional: audits are the slow, expensive
phase and the board does not need refreshing every batch. Run them roughly every
third batch so shipping is never barriered on planning — a dead auditor must
never stall a build (Next-Lane lost a night to exactly that).

## Resuming

Re-run with `resumeFromRunId` to continue where a previous run stopped;
completed agents replay from cache.
