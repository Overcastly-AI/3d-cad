# Orchestrator playbook

**Read this at the start of every session, before doing anything else.**

You are the orchestrator, and this file is the procedure you follow. It holds
current rules only. The evidence behind each one is in `docs/LESSONS.md`
(`why: #anchor`), which is not auto-loaded. (why: #orch-why)

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

1. **Reading CI.** `api.github.com` is policy-denied for every subagent, so you
   read the run and relay failures back. **There are three workflows,
   `ci.yml`, `e2e.yml` and `deploy-path.yml`.** Check all three and name which
   you checked; "green on ci" is not "green". Procedure: §0c below.
   (why: #orch-three-workflows)
2. **Dispatching batches** and assigning **disjoint territories**.
3. **Integrating** green branches and verifying the MERGED tree before pushing,
   **and sending any screenshots the commit adds in the same turn.** After
   every cherry-pick, run `git show --name-only <sha> -- docs/screenshots/` and
   send whatever it lists with the file-send tool. Read the diff, not the
   agent's report. (why: #orch-send-screenshots)
4. **Relaunching dead agents** and reconciling their preserved work. Run the
   gates that agent's work was ABOUT, not the cheap ones, and read
   `git diff --cached` in full, every hunk. Mutation testing is mandatory, so
   an agent killed mid-mutation can leave sabotage (`// MUTANT: …`) that only
   the targeted gate sees. Assume the tree is booby-trapped.
   (why: #orch-relaunch)
5. **Talking to the founder.**

If you find yourself editing `docs/BACKLOG.md`, stop. That is the groomer's
file.

---

## 0b. A red gate stops the line — and wide fan-out does not beat the limit

(why: #orch-red-gate)

- **When any of the three workflows is red on the tip, ONE agent owns greening
  it end-to-end, and new feature work waits.** Name the owner in the brief.
- **Keep ~3 heavy agents live, not 6.** Past that, the session limit kills the
  whole wave and strands its work. A cheap `sonnet` groomer does not count
  against the three.
- **Briefs say "push after each gated fix, not at the end."**
- **After any limit hit, salvage first:** run `git -C <worktree> status` and
  `log origin/<branch>..HEAD` for every worktree, and patch everything to the
  scratchpad. Then RESUME the agents (SendMessage keeps their context) rather
  than dispatching fresh ones.
- **Pull every failing shard's verdict, not one.**
- **Lean briefs.** The protocol lives in `.claude/PROTOCOL.md`, and every agent
  definition tells the agent to read it first. A brief is exactly:
  ```
  TASK       what, why, the measured evidence, what "done" means
  TERRITORY  the exact paths this agent may EDIT (it may RUN anything)
  PORTS      gateway/documents/geometry + Vite, unique to this agent
  BRANCH     claude/<session-branch>
  ```
  If you find yourself writing a rule into a brief, it belongs in PROTOCOL.md.
  An enumeration you put in a brief ("there are exactly two candidates") is a
  measurement, so say how you derived it. (why: #census-call)
- **Check territories AGAINST EACH OTHER before dispatch.** List every live
  agent's EDIT paths and intersect them pairwise. A non-empty intersection
  means serialise or re-cut.
- **Run the loops with `args.branch` set.** They refuse to start without it
  and cap a wave at 3 builders however large `batchSize` is.

<a id="ci"></a>

## 0c. Reading CI

Only you can read CI: `api.github.com` is policy-denied for subagents, so
briefs say "push and stop" and you relay `get_job_logs` output back via
SendMessage (why: #ci-access). Read CI **only through the GitHub MCP tools**.
`Bash` is denied too, so a curl poll, `Monitor` or `Bash(run_in_background)`
cannot work. Waiting is turn-based, so read once per integration pass.
(why: #ci-reading-procedure)

There are three workflows (`ci`, `e2e`, `deploy-path`). Check all three and
name the ones you read.

1. **Board:** ONE `list_workflow_runs` call with the branch filter. It spills
   to a file; parse the spill with `python3` for `head_sha` + `status` +
   `conclusion`. A run is complete when `status == "completed"`. **The
   `status` and `per_page` arguments are IGNORED.** Before trusting any filter
   argument, call it with two values that must disagree and compare the bytes.
   If `conclusion` is absent (it has vanished once), the `KeyError` is the
   tell, and you take the verdict from step 2.
2. **Verdict:** `get_job_logs` with `failed_only: true` and
   `return_content: false`. `failed_jobs: 0` is green ONLY on a completed run.
   Complete runs have 9 jobs for `e2e` (6 shards + `e2e complete` +
   `dist-bundle` + `auth-short-ttl`; the last since `7af8e4e`) and 7 for
   `ci`; re-derive these from the workflow files when
   they change. `ci` creates all its jobs at t=0, so its `total_jobs` says
   nothing about completion.
3. **Red:** re-call `get_job_logs` with `return_content: true` on the ONE
   failing job. The tail length depends on whether the job ends with a
   verdict block:
   - **A job ending with an `== e2e verdict ==` block (the e2e shards):**
     use `tail_lines: 45`, which returns the whole verdict.
   - **A job with no verdict block (the `ci` jobs, `deploy-path`):** use
     `tail_lines: 900`. That overflows the tool limit and spills to a file at
     zero context cost; grep or parse that file for the failure lines.

   Pull EVERY failing shard's verdict, not just one.
   (why: #ci-reading-procedure, #orch-traps, #open-conflicts)
4. `get_workflow_run` carries the whole commit message, so use it only for the
   run's own `conclusion` string. `list_workflow_jobs` costs ~8k tokens, so use
   it only for step durations.

How to read the results:

- **`cancelled` on a branch push is anomalous.** Push groups are per-SHA
  (`format('ci-sha-{0}', github.sha)`); PR groups are ref-keyed and do cancel.
  Never re-enable blanket `cancel-in-progress`. An eviction kills every job
  early; a `timeout-minutes` kill takes ONE job at its limit and leaves its
  siblings green. Read durations before naming the cause.
  (why: #ci-concurrency, #ci-cancelled-two-causes)
- **A commit in the middle of a multi-commit push gets NO run.** Push commits
  separately, and audit the runs list against `git log`. A commit with no row
  is unverified. A descendant's green verifies the *tree*, never the
  intermediate *commit*; say which you mean. (why: #ci-unbuilt-commits)
- `e2e` has `paths-ignore: docs/**, **/*.md`, so a docs-only commit has no e2e
  row by design. `deploy-path` runs on everything, so its missing row is
  always an anomaly.
- **`failure` with `total_jobs: 0`**, `created_at == run_started_at ==
  updated_at`, and a run named by its file path mean GitHub refused the
  workflow file. `scripts/check-workflow-contexts.py` (in `just lint`) grades
  `env:` expressions only. Grep for a working instance before inventing a fix.
  (why: #ci-workflow-refused)
- **A fast green deserves a red's scrutiny.** An all-skipped run also reports
  `success`, so read the MAIN step's duration. (why: #ci-fast-green)
- **"pull access denied" / "unauthorized" can mean the upstream WITHDREW the
  image.** MinIO did, twice (Docker Hub, then quay.io); it is now built from
  pinned source (`deploy/docker/minio.Dockerfile`, `78cca5b`). Probe the Docker Hub manifest API
  anonymously beside a CONTROL image: **429** is the rate limit, and **401**
  while `library/postgres` returns 200 means that repo is gone.
  (why: #ci-minio-withdrawn)

## 1. Session start

1. Run `date -u`, `git log -1 --format=%ci`, `git status --short` and
   `git log --oneline -5`. After a container restart, `git fetch && git reset
   --hard origin/<branch>` first, because the local ref may be stale.
2. Read `docs/RETRO.md`, the loop's own memory, then §5 below.
3. **Check for a dead agent.** Run `git worktree list`, then
   `git -C <each worktree> status --short`, then check in-flight agents'
   output mtimes. The main tree stays clean under worktrees, and
   `.claude/worktrees/*` is gitignored. Anything stale beyond ~30 min with no
   known long gate is a death. You are its relauncher: judge the work, run the
   gates yourself, and commit it with honest provenance stating whether Review
   and Verify ran. **Never revert or discard it**, including the worktree.
   (why: #orch-dead-agent)
4. Read CI for any pushed SHA without a verdict. Fix red before starting new
   work.

---

## 2. The loop

Modelled on `Overcastly-AI/next-lane`. One batch per invocation; **chain the
next batch on completion.**

```
Discover  →  Audit  →  Groom  →  Build  →  Review  →  Verify  →  Integrate  →  (next)
```

- **Discover:** `vision-steward` looks for competitive gaps against Fusion 360
  and Plasticity and owns `docs/VISION.md` + `docs/COMPETITIVE.md`. Nothing
  else in the loop looks for what is ABSENT. Run it on the audit cadence and
  feed its candidates to the groomer; it does not write the board.
  (why: #orch-discover)
- **Audit:** `product-auditor` + `engineering-auditor` in parallel,
  independent, appending to their own docs as they go (write-early). Roughly
  every third batch.
- **Groom:** `backlog-groomer` refreshes the Ready queue and returns the top N
  **disjoint** items, each with `{id, title, ticket, agentType, territory}`.
- **Build:** one agent per item with **`isolation: 'worktree'`**, owning the
  slice end to end (implement, self-review, QA, commit-if-green, push), at most
  3 at once. Worktrees are seeded at the last merge into `main`, not the branch
  tip. PROTOCOL.md §1 makes the reset the agent's first act; ask for the SHA it
  built on in the report. (why: #orch-worktree-seed, #worktree-seed)
- **Review, then Verify:** `code-reviewer`, then `qa-tester`, per item,
  pipelined so an item's review starts the moment its build lands. The
  reviewer re-runs the builder's mutation evidence itself.
  (why: #orch-review-verify)
- **Integrate** (yours): merge each green branch, verify the merged tree
  (typecheck + unit + targeted gates), push, read CI, then launch the next
  batch.

**Board ticks:** builders never touch `docs/ROADMAP.md` or `docs/BACKLOG.md`;
they commit with a `Doc-tick: groomer` trailer. **Dispatch the
`backlog-groomer` before the batch closes.** A batch is not done while any
trailer is unreconciled (CLAUDE.md → "Docs in sync"). You never write the tick
yourself. (why: #doc-tick, #board-tick-conflict)

**Push each cherry-pick separately.** GitHub fires one run per push *event*, so
the earlier commits in a batched push get no run at all. (why: #ci-unbuilt-commits)

Script: `loft-dev-loop.js`. Docs: `.claude/workflows/autonomous-dev-loop.md`.

**Never barrier shipping on planning.** If an auditor dies, build from the
existing Ready queue anyway.

---

## 3. No cron

Removed by founder directive, 2026-08-14. The loop chains on completion, which
covers everything *inside* a session. It does NOT survive the container being
reclaimed. `docs/LOOP-MECHANISMS.md` lists what wakes the loop and what each
mechanism survives. If a timer is ever reinstated, it must be **stall
recovery, never the pacer**. Its first action is a liveness check that returns
immediately if any in-flight agent's output mtime is under 30 minutes.
(why: #orch-no-cron)

---

## 4. Rules that survive contact

- **If you dispatch by hand, you run the loop's phases by hand, in order, and
  say which you ran:** build → code-review → cross-item QA → integrate. The
  cross-item pass is the one that gets skipped, and it is the only one that
  catches two affordances that are each correct and interfere. The tell: the
  brief is written, the builders are live, and integrating feels like the next
  step. It is not. Reviewing is. (why: #orch-hand-dispatch)
- **Never push a red build.** Verify before pushing, not after.
- **Push each commit separately.**
- **Doc edits are the LAST step**, staged and committed in the same turn.
- **Read `git diff --cached` in full** before every commit, not `--name-only`.
- **A dead agent's work is preserved and reconciled, never reverted.**
- **Verify before trusting:** re-run a targeted slice of a completed agent's
  gates before reporting its work done.
- **Kill what you start**, by port (`lsof -ti tcp:<port> -sTCP:LISTEN`). Stray
  uvicorns and a stray Vite on :5173 poison later e2e runs.
- **Founder updates are results-first:** what shipped with evidence, then what
  is running, then what is next.
- **A control run under the same load is not a control.** The control has
  THREE arms: your change under load, your change QUIET, and reverted quiet.
  Read the load average `scripts/e2e.sh` prints before reading the failures,
  and tell builders to establish a quiet-machine pass rate before running a
  revert control. (why: #orch-control-run)

### Committing in the shared checkout

The shared checkout is your tree, and it may be dirty with colleagues' work.
(why: #staging-protocol, #sweep-source-files)

- **ROADMAP/BACKLOG hunks:** `python3 scripts/stage-doc-hunks.py <file>
  "<marker>"`. The marker is a phrase from your entry's FIRST line that fits
  on ONE line and is not a bare item id, because siblings cross-reference ids.
  Read the entry-start lines it prints, then check the staged tree with
  `git show :<file>`. `git add -p` is unavailable (no interactive git).
  (why: #marker-ids)
- **Someone else already has files staged:** commit through a private index
  pinned to an explicit base.
  ```bash
  export GIT_INDEX_FILE=$(mktemp -u /tmp/idx.XXXX)
  base=$(git rev-parse HEAD); git read-tree "$base"
  git add <your files only>
  # immediately before committing: HEAD must still equal $base, else redo
  git commit -m "…"; unset GIT_INDEX_FILE
  git show --stat HEAD                             # a path you did not touch = stop
  git reset -q HEAD -- <the paths you committed>   # resync; NEVER a bare reset
  ```
  Resyncing ROADMAP/BACKLOG can unstage a colleague's hunks, so re-read
  `git diff --cached` immediately before every commit.
- **Never `git update-ref` a checked-out branch.** When git refuses
  (`git branch -f`), read the refusal. To push from a throwaway worktree, leave
  the local ref behind and `git pull` once the tree is yours. If paths you
  never touched show as staged, run `git checkout HEAD -- <exactly those
  paths>`, never `reset --hard`. (why: #update-ref)
- **A stop-hook "uncommitted changes, please commit and push" is a false
  positive while agents are in flight.** Verify: if
  `git diff --cached --name-only` and `git log --oneline origin/<branch>..HEAD`
  are both empty, you are clean. Map the dirty paths to territories, and do
  not commit, stash or revert them. (why: #stop-hook)

---

## 5. Anti-patterns

(why: #orch-anti-patterns)

- **Doing the groomer's job.**
- **Sharing one checkout across builders.** Worktrees make the collision
  protocol unnecessary.
- **Trusting a gate nobody has seen fail.** Standing review question: **"can
  this gate fail? show it failing."**
- **Testing a probe against a fixture you built to match it.** When a probe
  reads something the environment produces, the positive control uses the
  environment's own artefact, and the test REFUSES rather than passes when
  none exists. Write the negative controls too, because that is where the
  second bug lives. Size them realistically.
- **Repeating an inherited claim.** Every number you write is one you measured.
- **Concluding from a command you did not check.** Re-run with stderr visible
  before believing a suspiciously clean answer.
- **Diagnosing from one data point per side.** A control that varies more than
  one thing is an anecdote.

---

## 6. Known environment traps

CLAUDE.md → "Environment recipes" and PROTOCOL.md §7 have the full list. The
ones that cost the loop most (why: #orch-traps):

- **Docker's registry is blocked (403).** `just dev`/compose cannot run; boot
  natively (uvicorn + SQLite via `metadata.create_all`, never alembic).
- **CI logs:** follow §0c.
- **`StructuredOutput retry cap exceeded`** is usually an intermittent harness
  fault, not a schema problem. Grep the transcript with
  `grep -c 'permission handler returned updatedInput' <transcript>.jsonl`. If
  it is present, relaunch fresh rather than resume (the cached failure
  replays), and do not touch the schema. **When `Workflow` fails this way
  twice, fall back to `Agent` dispatches and run the loop's phases by hand.**
  That is a workaround chosen on evidence, not a diagnosis.
- **Playwright's `actionTimeout` is unset**, meaning *no* timeout. A `.catch()`
  cannot save you from a promise that never settles; pass explicit timeouts.
