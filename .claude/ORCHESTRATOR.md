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
   **THERE ARE THREE WORKFLOWS AND `ci` IS ONLY ONE OF THEM** — `ci.yml`,
   `e2e.yml`, `deploy-path.yml`. Reading `ci` alone and saying "CI is green" is
   a false statement about the build, and I made it repeatedly on 2026-08-14
   while `e2e` had been RED for **ten consecutive commits** (last green
   `a34382b`; red from `221a7ca` onward, which is a DOCS-ONLY commit, so the
   red was never in anyone's diff). Nobody caught it because the sentence
   "green on ci" is true and reads like the whole answer. Check all three, name
   which one you checked, and treat "green" as a claim that needs the same
   measurement discipline as any other.
2. **Dispatching batches** and assigning **disjoint territories**.
3. **Integrating** green branches and verifying the MERGED tree before pushing.
   **AND SENDING ANY SCREENSHOTS THE COMMIT ADDS, IN THE SAME TURN.** CLAUDE.md's
   design mandate says "surfaced" means the orchestrator SENDS them with the
   file-send tool — a PNG the founder never sees does not count. Make it
   mechanical, because judgement fails here: after every cherry-pick, run
   `git show --name-only <sha> -- docs/screenshots/` and send whatever it lists.
   Measured 2026-08-15 when the founder had to ask: 17 shots were added across
   the session and I sent 12. The five I sat on were the two that most directly
   showed his own reported bugs — `dimension-pick-before-desktop.png`, which has
   the whole "cannot assign a dimension" defect in one frame, and the SKETCH-1
   re-open pair. I sent the shots for the two tickets whose agents happened to
   mention screenshots in their reports, and missed the ones whose agents merely
   committed them. Do not rely on the report; read the diff.
4. **Relaunching dead agents** and reconciling their preserved work. **Run the
   gates that agent's work was ABOUT, not the gates that are cheap** — and read
   `git diff --cached` in full, every hunk, before committing it. On 2026-08-15 a
   reconciliation of mine (`0580f7d`) shipped a stopped agent's
   `// MUTANT: always 0` constant as product code: I ran lint and the unit suite,
   both structurally incapable of seeing an e2e-diagnostics change, and the one
   gate that could see it was the one I skipped. It then failed on every commit
   for the next ten. Mutation testing is MANDATORY here, so an agent killed
   mid-mutation leaves sabotage that is by construction invisible to every gate
   except the one it was aimed at. Assume the tree is booby-trapped, not merely
   unfinished.
5. **Talking to the founder.**

If you find yourself editing `docs/BACKLOG.md`, stop. That is the groomer's file
and you are re-creating the failure this playbook was written to end.

---

## 1. Session start

1. `date -u`, `git log -1 --format=%ci`, `git status --short`, `git log --oneline -5`.
2. Read `docs/RETRO.md` — the loop's own memory, including every way it has
   broken. Then this file's §5.
3. **Check for a dead agent.** The old tell was "last commit is old AND the
   tree is dirty" — that breaks under worktrees, because the main tree stays
   clean and the work sits in `.claude/worktrees/*` (now gitignored, so it does
   not even show as untracked). Check all three: `git worktree list`, then
   `git -C <each worktree> status --short`, then in-flight agents' output
   mtimes. Anything stale beyond ~30 min with no known long gate is a death.
   You are its relauncher: judge the work, run the gates yourself, and commit it
   with honest provenance stating whether Review and Verify ran.
   **Never revert or discard it** — including the worktree.
4. Read CI for any pushed SHA without a verdict. Fix red before starting new work.

---

## 2. The loop

Modelled on `Overcastly-AI/next-lane`, which runs this in production. One batch
per invocation; **chain the next batch on completion.**

```
Audit  →  Groom  →  Build  →  Review  →  Verify  →  Integrate  →  (next batch)
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

  **A WORKTREE IS SEEDED FROM THE SESSION'S INITIAL REF, NOT THE BRANCH TIP —
  put the reset in every brief.** Measured 2026-08-14 across both dispatch
  mechanisms, hours apart, and after `main` had moved: every worktree sat at
  `5aa981a`. The VP-1a agent's worktree was five commits behind and did not
  contain VP-1, the commit it was extending — the spec file it was told to edit
  did not exist. It noticed and reset; an agent that did not would have gated
  against stale code and produced a commit whose parent reverts its
  predecessors. Brief line: *"your first act is `git fetch origin <branch> &&
  git reset --hard origin/<branch>`; state in your report which SHA you built
  on."*
- **Review, then Verify** — `code-reviewer` then `qa-tester`, per item,
  pipelined so an item's review starts the moment its build lands. **These were
  missing from the loop until 2026-08-14**, when the engineering audit (K8)
  measured the consequence: three of the last five commits landed with no review
  and no QA. A build-only loop cannot produce reviewed work however good the
  builders are. The reviewer re-runs the builder's mutation evidence itself.
- **Integrate** — yours. Merge each green branch, verify the merged tree
  (typecheck + unit + targeted gates), push, read CI, then launch the next batch.

**Builders commit CODE ONLY. The board tick is yours, folded in at
integration.** The same-commit rule for `docs/ROADMAP.md` + `docs/BACKLOG.md`
still holds — but three worktrees each editing those two files is a guaranteed
conflict, and resolving it by hand re-creates the sweeping this loop exists to
end. So say in every brief: *"commit code and tests only; do NOT touch
docs/BACKLOG.md or docs/ROADMAP.md."* Then at integration, per item:
`git cherry-pick <sha>`, write the tick, `git add` the two docs,
`git commit --amend --no-edit`. The rule is kept (every commit carries its tick)
and no two agents ever hold the same file. Verified working 2026-08-14 on
SKETCH-1 (`30a9f3f`) and VP-1 (`43c703c`).

**Push each cherry-pick separately.** GitHub fires one run per push *event*, so
a batched push leaves the earlier commits with no run at all — not a cancelled
one, none. Five separate pushes on 2026-08-14 produced five separate runs.

Script: `loft-dev-loop.js`. Docs: `.claude/workflows/autonomous-dev-loop.md`.

**Never barrier shipping on planning.** If an auditor dies, build from the
existing Ready queue anyway.

---

## 3. No cron

Removed by founder directive, 2026-08-14. We had made a 15-minute cron the
*pacer* against slices lasting three and a half hours — it woke roughly fourteen
times per slice and each wake did more hand-work. That was the "racing".

The loop chains on completion, which covers everything *inside* a session.

**It does not cover the case that has actually cost us most.** An earlier
version of this file said "it cannot go idle if every batch launches the next
one" — that is false here. In-session chaining dies with the session, and the
container has been reclaimed twice (16 h 45 m and ~30 h gaps). Removing cron
fixed the racing and left **zero** recovery paths where there had been one
flawed one.

What actually wakes this loop, and what each mechanism survives, is in
`docs/LOOP-MECHANISMS.md`. Short version: the `Stop` hook already continues the
session (it is the "Stop hook feedback" you keep seeing); only a GitHub Actions
schedule, a Routine, or a PR webhook survives the container dying, and none is
currently armed.

If a timer is ever reinstated it must be **stall recovery, never the pacer** —
its first action is a liveness check that returns immediately if any in-flight
agent's output mtime is under 30 minutes.

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
  are all orchestrator commits. Eight of fourteen agents had never run.
- **Sharing one checkout across builders.** The entire collision protocol, and
  `scripts/stage-doc-hunks.py` — 905 lines that failed silently three times —
  are the cost. Worktrees make them unnecessary.
- **Trusting a gate nobody has seen fail.** Three shipped in one day: a CI grep
  matching its own prose, a unit test whose helper did the cleanup it asserted,
  and a `self_test` returning 0 with zero checks because `all([])` is `True`.
  **Standing review question: "can this gate fail? show it failing."**
- **Testing a probe against a fixture you built to match it.** The loop hook's
  own in-flight guard globbed `/tmp/claude-0/*/tasks` — one directory shallower
  than the harness's real path — and its test passed because the fixture was
  created at the depth the code expected. It could never fire, so the hook was
  free to dispatch on top of live agents: the exact racing it was written to
  prevent, shipped 59 minutes after `docs/RETRO.md`. Found by
  `engineering-auditor` (K7), fixed in `29387da`. **When a probe reads something
  the environment produces, the positive control must use the environment's own
  artefact, and the test must REFUSE rather than pass when none exists.**
  Corollary, earned the same hour: writing the *negative* controls found a
  second defect the audit had not — `find … | grep -q .` is wrong under
  `pipefail` (grep exits first, find takes SIGPIPE), so the guard read "nothing
  in flight" precisely when many outputs were fresh. **The negative control is
  where the second bug lives.** And size it: 3 fixture files let the broken form
  pass, 2000 failed it deterministically.
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
  **REFINEMENT, 2026-08-15: count the faults per agent before relaunching, and
  send ONE canary rather than the whole batch.** A three-agent workflow lost all
  three in five minutes — 10, 11 and 24 occurrences respectively; both auditors
  returned EMPTY having written nothing despite write-early, and the groomer hit
  the cap. When the fault is hitting EVERY agent, "relaunch fresh" re-buys the
  same failure at full batch cost. Instead dispatch one agent on a real ticket
  and let it double as the probe — tell it the fault exists, that it is not its
  mistake, to retry once or twice and then stop and report rather than working
  around it. Count the occurrences with
  `grep -c 'permission handler returned updatedInput' <transcript>.jsonl`; a
  clean canary means the batch is safe to send.
  **AND THAT REFINEMENT WAS ITSELF WRONG WITHIN ONE CYCLE — the canary was not a
  valid control.** I sent one `Agent`-tool dispatch, it saw ZERO faults across
  ~45 calls and finished a full ticket, and I concluded "the fault has passed"
  and relaunched the workflow. It died identically: 12, 21 and 10 occurrences,
  both auditors EMPTY again. The canary differed from the batch in THREE ways at
  once — dispatch mechanism (`Agent` vs `Workflow`), concurrency (one agent vs
  two auditors in parallel), and schema (none vs `StructuredOutput`) — so a clean
  result could not isolate anything. That is the third time in one day I reasoned
  from one data point per side, having written the rule down twice. **A control
  that varies more than one thing is not a control, it is an anecdote.**
  What IS measured: two `Workflow` runs failed heavily (10/11/24 and 12/21/10),
  one `Agent` run was clean, and the stripped calls span `Bash` (19), `Glob` (6),
  `Grep` (4), `Read` (9) and `Write` (3) — so it is not Bash-specific and not
  schema-specific either (the auditors carry no schema and still returned empty).
  Practical rule until someone isolates it properly: **when `Workflow` fails this
  way twice, fall back to `Agent` dispatches and run the loop's phases by hand.**
  That is a workaround chosen on evidence, not a diagnosis — do not write it up
  as one.
- **Playwright's `actionTimeout` is unset**, meaning *no* timeout. A `.catch()`
  cannot save you from a promise that never settles; pass explicit timeouts.
