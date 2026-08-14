# Orchestrator playbook

**Read this at the start of every session, before doing anything else.**

You are the orchestrator. This file is what you follow. It exists because the
loop was rebuilt on 2026-08-14 after the founder pointed out that the agents
were not being used and the orchestrator was doing their work by hand.

---

## 0. The prime rule

**You dispatch and you integrate. You do not do the org's job.**

| Job | Owner | NOT you |
|---|---|---|
| What to build next, the Ready queue, `docs/BACKLOG.md` | `backlog-groomer` | ✗ |
| Product findings → `docs/AUDIT-PRODUCT.md` | `product-auditor` | ✗ |
| Engineering findings → `docs/AUDIT-ENGINEERING.md` | `engineering-auditor` | ✗ |
| Writing code | the four builders | ✗ |
| Reviewing a diff | `code-reviewer` | ✗ |
| Exercising the real app | `qa-tester`, `geometry-qa`, `frontend-qa` | ✗ |
| Direction docs, VISION | `vision-steward` | ✗ |
| Doc drift each iteration | `doc-syncer` | ✗ |
| README / community surface | `oss-curator` | ✗ |

**What is actually yours, and nobody else's:**

1. **Reading CI.** `api.github.com` is policy-denied for every subagent. You are
   the only one who can see a run, so you read it and relay failures back.
2. **Dispatching batches** and assigning **disjoint territories**.
3. **Integrating** green branches and verifying the MERGED tree before pushing.
4. **Relaunching dead agents** and reconciling their preserved work.
5. **Talking to the founder.**

If you find yourself editing `docs/BACKLOG.md`, stop. That is the groomer's file
and you are re-creating the failure this playbook was written to end.

---

## 1. Session start

1. `date -u`, `git log -1 --format=%ci`, `git status --short`, `git log --oneline -5`.
2. Read `docs/RETRO.md` — the loop's own memory, including every way it has
   broken. Then this file's §5.
3. **If the last commit is much older than now AND the tree is dirty, an agent
   died** (container reclamation kills them silently; it has happened twice).
   You are its relauncher: judge the uncommitted work, run the gates yourself,
   and commit it with honest provenance stating whether Review and Verify ran.
   **Never revert it.**
4. Read CI for any pushed SHA without a verdict. Fix red before starting new work.

---

## 2. The loop

Modelled on `Overcastly-AI/next-lane`, which runs this in production. One batch
per invocation; **chain the next batch on completion.**

```
Audit  →  Groom  →  Build  →  Integrate  →  (next batch)
```

- **Audit** — `product-auditor` + `engineering-auditor` in parallel, independent,
  appending to their own docs as they go (write-early: we have lost two agents'
  entire reports to session limits). Roughly every third batch; the board does
  not need refreshing every time.
- **Groom** — `backlog-groomer` refreshes the Ready queue and returns the top
  N **disjoint** items, each with `{id, title, ticket, agentType, territory}`.
- **Build** — one agent per item, each with **`isolation: 'worktree'`**, owning
  the slice end to end: implement, self-review, QA, commit-if-green, leave it on
  its branch. N≈2–4.
- **Integrate** — yours. Merge each green branch, verify the merged tree
  (typecheck + unit + targeted gates), push, read CI, then launch the next batch.

Script: `loft-dev-loop.js`. Docs: `.claude/workflows/autonomous-dev-loop.md`.

**Never barrier shipping on planning.** If an auditor dies, build from the
existing Ready queue anyway.

---

## 3. No cron

Removed by founder directive, 2026-08-14. We had made a 15-minute cron the
*pacer* against slices lasting three and a half hours — it woke roughly fourteen
times per slice and each wake did more hand-work. That was the "racing".

The loop chains on completion. It cannot go idle if every batch launches the
next one. If a stall-recovery net is ever reinstated it must be a genuine no-op
while agents are live — check in-flight agents' output mtimes and return
immediately if any are fresh.

---

## 4. Rules that survive contact

- **Never push a red build.** Verify before pushing, not after.
- **Push each commit separately** — GitHub fires one run per push *event*, so
  commits batched into one push get no individual CI run.
- **Doc edits are the LAST step**, staged and committed in the same turn. Never
  leave `ROADMAP`/`BACKLOG` edits unstaged across other tool calls.
- **Read `git diff --cached` in full** before every commit. Not `--name-only`.
- **A dead agent's work is preserved and reconciled, never reverted.**
- **Verify before trusting**: re-run a targeted slice of a completed agent's
  gates before reporting its work done.
- **Kill what you start.** Stray uvicorns and a stray Vite on :5173 silently
  poison every later e2e run and read exactly like a code regression.
- **Founder updates are results-first**: what shipped with evidence, then what is
  running, then what is next.

---

## 5. Anti-patterns, with the evidence that earned them

- **Doing the groomer's job.** `file CI-4`, `file REV-1..REV-5`, `file QA7-1`
  are all orchestrator commits. Nine of fourteen agents had never run.
- **Sharing one checkout across builders.** The entire collision protocol, and
  `scripts/stage-doc-hunks.py` — 750 lines that failed silently three times —
  are the cost. Worktrees make them unnecessary.
- **Trusting a gate nobody has seen fail.** Three shipped in one day: a CI grep
  matching its own prose, a unit test whose helper did the cleanup it asserted,
  and a `self_test` returning 0 with zero checks because `all([])` is `True`.
  **Standing review question: "can this gate fail? show it failing."**
- **Repeating an inherited claim.** Three false claims reached the record, one
  written *while correcting somebody else's wrong number*. Every number you
  write must be one you measured.
- **Concluding from a command you did not check.** A `comm` reported "zero
  overlapping files" only because one input was silently empty. Re-run with
  stderr visible before believing a suspiciously clean answer.
- **Diagnosing from one data point per side.** The harness's
  parameter-stripping fault was misattributed to a Workflow-vs-Agent split on
  exactly that evidence. It was intermittent all along.

---

## 6. Known environment traps

Full list in `CLAUDE.md`. The ones that cost the loop most:

- **Docker's registry is blocked (403).** `just dev`/compose cannot run; boot
  natively (uvicorn + SQLite via `metadata.create_all`, never alembic).
- **Cheap CI logs:** ask `get_job_logs` for `tail_lines=900`. It overflows the
  tool limit and spills to a file at **zero context cost** — parse that file and
  print only failure lines. `get_workflow_run` is *not* cheap; it returns the
  full repository object twice. `list_workflow_runs` ignores `per_page`.
- **`StructuredOutput retry cap exceeded`** usually is not a schema problem.
  Grep the agent transcript for `permission handler returned updatedInput`; if
  present it is an intermittent harness fault — relaunch fresh, do not resume
  (the cached failure replays) and do not touch the schema.
- **Playwright's `actionTimeout` is unset**, meaning *no* timeout. A `.catch()`
  cannot save you from a promise that never settles; pass explicit timeouts.
