# Workflow: nightly-build-loop

Autonomously work down the **Ready** queue in `docs/BACKLOG.md`, one item per
iteration, until the queue is empty or the token budget runs low. Designed
for long unattended runs.

## How it operates

1. Read `docs/BACKLOG.md`; take the top Ready item (fall back to the next ⬜
   item of the current ROADMAP phase if Ready is empty).
2. Run **build-vertical-slice** for it.
3. Green → commit (ROADMAP/BACKLOG ticked in the same commit), push.
4. Run `doc-syncer` for the iteration.
5. Repeat while budget allows.

## Guardrails

- Each iteration leaves the repo **building, committed, pushed** — never a
  red or dangling state between iterations.
- **Retry once, then skip:** a slice failing twice is parked — leave the item
  on the board with a dated blocker note, log it, move to the next item.
  Never loop forever on one item; never let one item stall the queue.
- Use `verification-before-completion` evidence before marking anything done.
- Prefer thin working slices over broad broken ones.
- Stop cleanly (summary of shipped/parked) when `budget.remaining()` can't
  safely fund another slice.

## Script outline

```js
export const meta = {
  name: 'nightly-build-loop',
  description: 'Ship Ready backlog items one by one until done or budget-low',
  phases: [{title:'Pick'},{title:'Build'},{title:'Sync'}],
}
const parked = []
let dry = 0
while (dry < 2 && (!budget.total || budget.remaining() > 150_000)) {
  phase('Pick')
  const next = await agent('Read docs/BACKLOG.md; return the top Ready item (title + acceptance criteria) not in this parked list: ' + JSON.stringify(parked) + '; or null.', {schema: ITEM_SCHEMA})
  if (!next.item) { dry++; continue }
  dry = 0
  phase('Build')
  try {
    await workflow('build-vertical-slice', { item: next.item })
  } catch (e) {
    parked.push(next.item); log(`parked: ${next.item}`); continue
  }
  phase('Sync')
  await agent('Doc-sync pass for the last iteration.', {agentType:'doc-syncer'})
}
return { parked }
```

## Resuming

Re-run with `resumeFromRunId` to continue after an interruption; completed
slices return from cache.
