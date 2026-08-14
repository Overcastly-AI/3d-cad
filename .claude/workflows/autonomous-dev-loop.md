# Workflow: autonomous-dev-loop

The full Loft "org" loop, modelled on
[Overcastly-AI/next-lane](https://github.com/Overcastly-AI/next-lane), which
runs this shape in production. Two independent auditors set direction, the
groomer maintains the board, and the build loop ships the top items — each fully
reviewed and QA'd. It loops **on completion** (start the next batch as soon as
the current one finishes), **not on a timer**.

## Cadence — completion-driven. There is no cron.

Each invocation runs **one batch** (audit → groom → build N items). When the
batch finishes, the orchestrator integrates the green branches and immediately
launches the next batch. Stop only when the Ready queue is empty and the
auditors propose nothing new, or the user says stop.

**Cron was removed 2026-08-14 by founder directive**, and the reason is worth
keeping: we had made a 15-minute cron the *pacer* against slices that took three
and a half hours, so it woke ~14 times per slice and did more orchestrator
hand-work on each wake. Next-Lane's own retro is explicit that a watchdog is
*stall recovery* and never the pacer — "it only acts when the loop is idle; when
work is in flight it no-ops and re-arms". Ours did the opposite. Chain on
completion instead.

## The rule that makes this work: the orchestrator does not do the org's job

Audited 2026-08-14: eight of the fourteen agents in `.claude/agents/` had never
been invoked, and the orchestrator had been writing `docs/BACKLOG.md` itself —
`file CI-4`, `file REV-1..REV-5`, `file QA7-1` are all orchestrator commits.
That is the groomer's whole job, done in the most expensive context available,
and it produced every symptom we then spent tokens fixing: two classes of writer
on the shared docs (hence overwrites, hence `scripts/stage-doc-hunks.py`, which
has failed silently three times), and a cron racing its own slices.

**The orchestrator dispatches and integrates. It does not audit, does not groom,
and does not write the board.**

## Phases per batch

1. **Audit (parallel, independent)** — `product-auditor` and
   `engineering-auditor` deeply review the current app and **append** ratings and
   prioritised recommendations to their own docs. They do not see each other's
   output first; that independence is what earns its keep. They **write early**
   (append incrementally) so a late crash does not lose the pass — we have lost
   two agents' whole reports to session limits.
2. **Groom** — `backlog-groomer` ingests both audits, `docs/UI-REVIEW.md`,
   `docs/GEOMETRY-QA.md`, the roadmap and git history; dedupes, reprioritises,
   ticks what shipped, and refreshes the **Ready** queue in `docs/BACKLOG.md`.
   It returns the top N **disjoint** items with an explicit territory each.
3. **Build (parallel, isolated)** — each item is ONE agent in its own
   **`isolation: 'worktree'`**, owning the slice end to end: implement, review
   its own diff, QA against the real stack, commit only if green, leave the work
   on its branch. Serialize only items that touch the same files.
   **Builders commit CODE AND TESTS ONLY.** They do not touch `docs/ROADMAP.md`
   or `docs/BACKLOG.md`: several worktrees ticking those two files is a
   guaranteed conflict over exactly the files the collision protocol exists for,
   which would undo the isolation the worktree just bought. The groomer is the
   only writer on them during a batch, and the same-commit rule is still kept —
   see step 5.
4. **Review, then Verify (per item, pipelined)** — `code-reviewer` on what
   actually landed, then `qa-tester` against the real running stack. **These are
   not optional and they were missing from this loop until 2026-08-14**, when
   the engineering audit (K8) measured the consequence: three of the last five
   commits landed with no review and no QA, disclosed only in a commit message.
   A build-only loop cannot produce reviewed work however good the builders are.
   Pipelined rather than barriered — item A's review starts the moment A's build
   lands, while B is still building; nothing here needs cross-item context.
   The reviewer re-runs the builder's mutation evidence itself rather than
   trusting the report, and checks every factual claim the diff adds to the
   record.
5. **Integrate** — the orchestrator cherry-picks each clean branch, **writes the
   ROADMAP/BACKLOG tick and folds it into that commit** (`git commit --amend
   --no-edit`), **verifies the merged tree** (typecheck + unit + targeted gates)
   before pushing, pushes **each commit separately** (GitHub fires one run per
   push *event*, so a batched push leaves the earlier commits with no run at
   all), reads CI, then launches the next batch.

## Guardrails

- Never push a red build. One commit per item; parallel items are in separate
  worktrees so their commits cannot collide.
- Bounded batch size (N≈2–4) so each run stays reviewable.
- Read-only roles (auditors, QA) never touch app code.
- A dead agent's worktree is **preserved and reconciled by its relauncher**,
  never discarded.
- Never barrier shipping on planning: if an auditor dies, the build still pulls
  from the existing Ready queue.

## Script

`loft-dev-loop.js` (session workflow scripts). Outline:

```js
export const meta = { name:'loft-dev-loop',
  phases:[{title:'Audit'},{title:'Groom'},{title:'Build'},
          {title:'Review'},{title:'Verify'},{title:'Integrate'}] }

phase('Audit')                       // skippable via args.skipAudit
await parallel([
  () => agent('Deep product audit; APPEND docs/AUDIT-PRODUCT.md as you go.',
              {agentType:'product-auditor'}),
  () => agent('Deep engineering audit; APPEND docs/AUDIT-ENGINEERING.md as you go.',
              {agentType:'engineering-auditor'}),
])

phase('Groom')                       // THE GROOMER OWNS THE BOARD
const ready = await agent('Refresh the Ready queue; return the top N DISJOINT '
  + 'items with {id,title,ticket,agentType,territory}.',
  {agentType:'backlog-groomer', schema: READY})

// Build -> Review -> Verify as a PIPELINE, not barriered stages: A's review
// starts the moment A's build lands, while B is still building.
const slices = await pipeline(ready.items,
  it => agent(ticketBrief(it),                 // code+tests only, no doc ticks
              {phase:'Build', agentType: it.agentType,
               isolation:'worktree', schema: BUILT}),
  (build, it) => agent(reviewBrief(it, build), // re-runs the mutation itself
              {phase:'Review', agentType:'code-reviewer', schema: REVIEWED}),
  slice   => agent(qaBrief(slice),             // real stack, real browser
              {phase:'Verify', agentType:'qa-tester', schema: VERIFIED}))

phase('Integrate')                   // orchestrator, by hand, verified
```

## Done when

Each branch is clean through **review and QA** — not merely built — the merged
tree passes its gates, its board tick rode in the same commit, CI is green on
the pushed commit, and the next batch is launched.
